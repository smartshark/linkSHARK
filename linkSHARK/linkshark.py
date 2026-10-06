"""Plugin for execution with serverSHARK."""

import sys
import logging
import timeit
import re

from mongoengine import connect, DoesNotExist
from pycoshark.mongomodels import VCSSystem, Commit, IssueSystem, Issue, Project, IssueEvent, FileAction, File, Identity
from pycoshark.utils import create_mongodb_uri_string

class LinkSHARK:
    """Determines linked issues for commits
    """

    def __init__(self):
        """
        Default constructor.
        """
        self._log = logging.getLogger("main")
        # precompile regex
        self._direct_link_jira = re.compile('(?P<ID>[A-Z][A-Z0-9_]+-[0-9]+)', re.I | re.M)
        self._direct_link_bz = re.compile('(bug|issue|bugzilla)[s]{0,1}[#\s]*(?P<ID>[0-9]+)', re.I | re.M)
        self._direct_link_gh = re.compile('(bug|issue|close|fixes)[s]{0,1}[#\s]*(?P<ID>[0-9]+)', re.I | re.M)
        self._direct_link_szz = re.compile('(\d+)', re.M)
        self._bug_id_pattern = re.compile(r"jira(\sissue)?\s\#?(?P<ID>\d+)", re.I | re.M)
        self._szz_keyword = re.compile('(\s|^)fix(e[ds])?|(\s|^)bugs?|(\s|^)defects?|(\s|^)patch|(\s|^)issue[s]{0,1}',
                                       re.I | re.M)
        self._szz_only_number = re.compile(r'^[0-9\s\.\,;\:#]+$', re.M)
        self._broken_keys = {}
        self._correct_key = {}
        pass

    def start(self, cfg):
        """
        Executes the linkSHARK.
        :param cfg: configuration object that is used
        """
        self._log.setLevel(cfg.get_debug_level())
        start_time = timeit.default_timer()

        uri = create_mongodb_uri_string(cfg.user, cfg.password, cfg.host, cfg.port, cfg.authentication_db,
                                        cfg.ssl_enabled)
        connect(cfg.database, host=uri)

        # Get the id of the project for which the code entities shall be merged
        try:
            project_id = Project.objects(name=cfg.project_name).get().id
            self._log.info("Project ID = {}".format(type(project_id)))
        except DoesNotExist:
            self._log.error('Project %s not found!' % cfg.project_name)
            sys.exit(1)
        vcs_system = VCSSystem.objects(project_id=project_id).get()
        self._itss = []
        self._log.info('found the following issue tracking systems:')
        for its in IssueSystem.objects(project_id=project_id).order_by('url'):
            self._log.info(its.url)
            self._itss.append(its)

        # Initialize as a list populated with default project names for each tracking system
        correct_keys_per_its = [cfg.project_name] * len(self._itss)
        if len(cfg.correct_key)>0:
            correct_keys_per_its = cfg.correct_key.split(';')
            if len(correct_keys_per_its) != len(self._itss):
                self._log_critical('--correct-key must correct keys for all issue tracking systems if specified')
                sys.exit(1)
            for i,correct_key in enumerate(correct_keys_per_its):
                self._correct_key[self._itss[i].url] = correct_key
        if len(cfg.broken_keys)>0:
            broken_keys_per_its = cfg.broken_keys.split(';')

            if len(broken_keys_per_its) != len(self._itss):
                self._log_critical('--broken-keys must correct keys for all issue tracking systems if specified. If there are no keys to correct for one of the ITS just use the name of the correct key twice itself')
                sys.exit(1)
            for i,broken_keys in enumerate(broken_keys_per_its):
                self._broken_keys[self._itss[i].url] = broken_keys.split(',')

        self._log.info("Starting issue linking")
        commit_count = Commit.objects(vcs_system_ids=vcs_system.id).count()

        issue_map = {}
        total_regular_links = 0
        total_szz_links = 0
        for i,issue_system in enumerate(self._itss):
            project_id_string = correct_keys_per_its[i]
            self._log.info("project-id_string = {}".format(project_id_string))
            for issue in Issue.objects(issue_system_ids=issue_system.id):
                # Accept the issue if it is a pure number (GitHub) OR if it matches the prefix (Jira)
                if issue.external_id.isdigit() or issue.external_id.startswith(project_id_string):
                    try:
                        issue_number = [int(s) for s in issue.external_id.split('-') if s.isdigit()][0]
                    except IndexError:
                        self._log.error("index error because SZZ currently only support JIRA, may not link all issues correctly:", issue.external_id)
                        continue
                    if issue_number not in issue_map:
                        issue_map[issue_number] = [issue]
                    else:
                        issue_map[issue_number].append(issue)
        self._log.info("VCSSytem_ID = {}".format(vcs_system.id))
        for i,commit in enumerate(Commit.objects(vcs_system_ids=vcs_system.id).only('id', 'revision_hash', 'vcs_system_ids', 'message', 'author_id', 'committer_id')):
            if i%100==0:
                self._log.info("%i/%i  commits finished",i,commit_count)
            issue_links = self._get_issue_links(commit)
            if len(issue_links) > 0:
                commit.linked_issue_ids = issue_links
                commit.save()
                total_regular_links += len(issue_links)
            szz_links = self._get_szz_issue_links(commit, issue_map)
            if len(szz_links) > 0:
                commit.szz_issue_ids = szz_links
                commit.save()
                total_szz_links += len(szz_links)

        self._log.info(f"Total Regular Issue Links Created: {total_regular_links}")
        self._log.info(f"Total SZZ Algorithm Links Created: {total_szz_links}")
        elapsed = timeit.default_timer() - start_time
        self._log.info("Execution time: %0.5f s" % elapsed)

    def _get_issue_links(self, commit):
        issue_links = []
        self._errored_keys = set()
        self._found_keys = set()
        commit_message = commit.message
        git_svn_start = commit_message.find('git-svn-id:')
        if git_svn_start >= 0:
            commit_message = commit_message[:git_svn_start]
        for its in self._itss:
            if 'jira' in its.url.lower():
                issues = self._jira_issues(its, commit_message)
            elif 'bugzilla' in its.url.lower():
                issues = self._bz_issues(its, commit_message)
            elif 'github' in its.url.lower():
                issues = self._gh_issues(its, commit_message)
            else:
                self._log.info(f"URL {its.url} did not match any platform criteria!")
                issues = []

            # linked issues are collected regardless of issue type
            for r in issues:
                if r.id in issue_links:
                    continue
                issue_links.append(r.id)

        keys_not_found = self._errored_keys-self._found_keys
        for key in keys_not_found:
            self._error('commit %s: %s does not exist' % (commit.revision_hash, key))

        return issue_links

    def _gh_issues(self, issue_system, message):
        ret = []
        for m in self._direct_link_gh.finditer(message):
            try:
                i = Issue.objects.get(issue_system_ids=issue_system.id, external_id=m.group('ID').upper())
                self._found_keys.add(m.group('ID').upper())
                ret.append(i)

            except Issue.DoesNotExist:
                self._errored_keys.add(m.group('ID').upper())
        return ret

    def _bz_issues(self, issue_system, message):
        ret = []
        for m in self._direct_link_bz.finditer(message):
            try:
                i = Issue.objects.get(issue_system_ids=issue_system.id, external_id=m.group('ID').upper())
                self._found_keys.add(m.group('ID').upper())
                ret.append(i)

            except Issue.DoesNotExist:
                self._errored_keys.add(m.group('ID').upper())
        return ret

    def _jira_issues(self, issue_system, message):
        ret = []
        for m in self._direct_link_jira.finditer(message):
            try:
                issue_id = m.group('ID').upper()
                if issue_system.url in self._broken_keys:
                    try:
                        index = self._broken_keys[issue_system.url].index(issue_id.split('-')[0])
                        self._log.warning('fixing broken key %s', issue_id)
                        issue_id = issue_id.replace(self._broken_keys[issue_system.url][index]+'-', self._correct_key[issue_system.url]+'-')
                    except ValueError:
                        # key not broken
                        pass

                i = Issue.objects.get(issue_system_ids=issue_system.id, external_id=issue_id)
                self._found_keys.add(m.group('ID').upper())
                ret.append(i)
            except Issue.DoesNotExist:
                self._errored_keys.add(m.group('ID').upper())
        # additional check in case the commit author referenced jira[\sissue]?\s\d+ instead of using the hyphen notation
        if issue_system.url in self._correct_key:
            for m in self._bug_id_pattern.finditer(message):
                try:
                    issue_id = self._correct_key[issue_system.url]+'-'+m.group('ID')
                    issue = Issue.objects.get(issue_system_ids=issue_system.id, external_id=issue_id)
                    ret.append(issue)
                except Issue.DoesNotExist:
                    pass
        return ret

    def _error(self, message):
        # we log to warn because error gets to stdout in servershark
        self._log.warning(message)


    def _get_szz_issue_links(self, commit, issue_map):
        issue_links = []

        commit_message = commit.message
        git_svn_start = commit_message.find('git-svn-id:')
        if git_svn_start>=0:
            commit_message = commit_message[:git_svn_start]
        syntactic_score = self._szz_syntactic_score(commit_message)

        file_names = set()
        for file_action in FileAction.objects(commit_id=commit.id).only('file_id'):
            file_names.add(File.objects(id=file_action.file_id).get().path.split("/")[-1])

        issues = None
        for its in self._itss:
            if 'jira' in its.url:
                issues = self._szz_issues(commit, commit_message, issue_map, file_names, syntactic_score)
        if issues is not None:
            for issue in issues:
                if issue.id in issue_links:
                    continue
                issue_links.append(issue.id)
        return issue_links

    def _szz_syntactic_score(self, commit_message):
        syntactic_score = 0


        if self._direct_link_jira.match(commit_message):
            syntactic_score += 1
        if self._szz_keyword.match(commit_message) or self._szz_only_number.match(commit_message):
            # this second match should also contain only bug id matches, but this is ommitted as this could never change
            # the links, because there is no difference between a syntactice score of 1 or 2
            syntactic_score += 1
        return syntactic_score

    def _szz_issues(self, commit, commit_message, issue_map, file_names, syntactic_score):
        ret = []
        for m in self._direct_link_szz.finditer(commit_message):
            issue_number = int(m.group(1))
            if issue_number not in issue_map:
                continue
            for issue in issue_map[issue_number]:
                if not issue.issue_type:
                    self._log.warning('could not find issue type for issue %s' % issue.id)
                    continue

                if issue.issue_type.lower() == 'bug':
                    is_fixed_bug = self._szz_is_fixed_bug(issue)
                    has_description_match = self._szz_has_description_match(issue, commit)
                    has_author_match = self._szz_has_author_match(issue, commit)
                    has_files_attached = self._szz_has_files_attached(issue, file_names)
                    semantic_score = is_fixed_bug+has_description_match+has_author_match+has_files_attached
                    if semantic_score>1 or (semantic_score==1 and syntactic_score>0):
                        ret.append(issue)
        return ret

    def _szz_is_fixed_bug(self, issue):
        resolved = False
        fixed = False
        if issue.status in ['resolved', 'closed']:
            resolved = True
            fixed |= issue.resolution.lower() != 'duplicated'

        for e in IssueEvent.objects.filter(issue_id=issue.id):
            resolved |= e.status is not None and e.status.lower() == 'status' and e.new_value is not None and e.new_value.lower() in \
                        ['resolved', 'closed']
            fixed |= e.status is not None and e.status.lower() == 'resolution' and e.new_value is not None and e.new_value.lower() == 'fixed'
        return resolved and fixed

    def _szz_has_description_match(self, issue, commit_message):
        return (issue.title is not None and issue.title in commit_message) or (issue.desc is not None and issue.desc in commit_message)

    def _szz_has_author_match(self, issue, commit):
        if not issue.assignee_id:
            return False

        assignee_identity = set()
        committer_identity = set()
        author_identity = set()

        for identity in Identity.objects(people=issue.assignee_id):
            assignee_identity.add(identity.id)
        for identity in Identity.objects(people=commit.committer_id):
            committer_identity.add(identity.id)
        for identity in Identity.objects(people=commit.author_id):
            author_identity.add(identity.id)

        if len(assignee_identity) and len(committer_identity) and len(author_identity):
            return len(assignee_identity & committer_identity) or len(assignee_identity & author_identity)
        else:
            return issue.assignee_id==commit.author_id or issue.assignee_id==commit.committer_id

    def _szz_has_files_attached(self, issue, file_names):
        for e in IssueEvent.objects.filter(issue_id=issue.id, status='Attachment'):
            if e.new_value in file_names:
                return True
        return False