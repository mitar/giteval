#!/usr/bin/env python

import json, operator, os, random, urllib

import git
# Has to be imported like this because util module is not accessible from git module directly
from git.util import hex_to_bin, Actor

GITHUB_ACCESS_TOKEN = None
GIT_PATH = None
REPOSITORIES = ()
ADD_IGNORE_FILENAMES = ()
ALL_IGNORE_FILENAMES = ()
IGNORE_PULL_REQUESTS = ()
IGNORE_AUTHORS = ()
MERGE_AUTHORS = {}
MAX_SCORE = 700
SCORE_CORRECTIONS = ()
WINNING_TEAM_SCORE = 70
WINNING_TEAM = ()

import local_settings

GITHUB_ACCESS_TOKEN = getattr(local_settings, 'GITHUB_ACCESS_TOKEN', None)
GIT_PATH = getattr(local_settings, 'GIT_PATH', GIT_PATH)
REPOSITORIES += getattr(local_settings, 'REPOSITORIES', ())
ADD_IGNORE_FILENAMES += getattr(local_settings, 'ADD_IGNORE_FILENAMES', ())
ALL_IGNORE_FILENAMES += getattr(local_settings, 'ALL_IGNORE_FILENAMES', ())
IGNORE_PULL_REQUESTS += getattr(local_settings, 'IGNORE_PULL_REQUESTS', ())
IGNORE_AUTHORS += getattr(local_settings, 'IGNORE_AUTHORS', ())
MERGE_AUTHORS.update(getattr(local_settings, 'MERGE_AUTHORS', {}))
MAX_SCORE = getattr(local_settings, 'MAX_SCORE', MAX_SCORE)
SCORE_CORRECTIONS += getattr(local_settings, 'SCORE_CORRECTIONS', ())
WINNING_TEAM_SCORE = getattr(local_settings, 'WINNING_TEAM_SCORE', WINNING_TEAM_SCORE)
WINNING_TEAM += getattr(local_settings, 'WINNING_TEAM', ())

if not GITHUB_ACCESS_TOKEN:
    raise Exception("GitHub access token is not configured.")

if GIT_PATH is not None:
    os.environ['PATH'] += ':%s' % GIT_PATH

PAGE_SIZE = 100

SCORE_CORRECTIONS_DICT = {}
for author, score in SCORE_CORRECTIONS:
    SCORE_CORRECTIONS_DICT[author] = SCORE_CORRECTIONS_DICT.get(author, 0) + score

def github_api(url, args={}):
    data = []

    page = 1
    while True:
        args.update({
            'per_page': PAGE_SIZE,
            'page': page,
            'access_token': GITHUB_ACCESS_TOKEN,
        })
        d = json.load(urllib.urlopen("%s?%s" % (url, urllib.urlencode(args))))

        if not isinstance(d, list):
            raise Exception(d)

        data.extend(d)

        if len(d) < PAGE_SIZE:
            break
        else:
            page += 1

    return data

def blame(repo, start_commit, end_commit, filename):
    data = repo.git.blame('%s^..%s' % (start_commit, end_commit), '--', filename, p=True)
    commits = dict()
    blames = list()
    info = None

    for line in data.splitlines(False):
        parts = repo.re_whitespace.split(line, 1)
        firstpart = parts[0]
        if repo.re_hexsha_only.search(firstpart):
            # handles
            # 634396b2f541a9f2d58b00be1a07f0c358b999b3 1 1 7		- indicates blame-data start
            # 634396b2f541a9f2d58b00be1a07f0c358b999b3 2 2
            digits = parts[-1].split(" ")
            if len(digits) == 3:
                info = {'id': firstpart}
                blames.append([None, []])
            elif info['id'] != firstpart:
                info = {'id': firstpart}
                blames.append([commits.get(firstpart), []])
            # END blame data initialization
        else:
            m = repo.re_author_committer_start.search(firstpart)
            if m:
                # handles:
                # author Tom Preston-Werner
                # author-mail <tom@mojombo.com>
                # author-time 1192271832
                # author-tz -0700
                # committer Tom Preston-Werner
                # committer-mail <tom@mojombo.com>
                # committer-time 1192271832
                # committer-tz -0700  - IGNORED BY US
                role = m.group(0)
                if firstpart.endswith('-mail'):
                    info["%s_email" % role] = parts[-1]
                elif firstpart.endswith('-time'):
                    info["%s_date" % role] = int(parts[-1])
                elif role == firstpart:
                    info[role] = parts[-1]
                # END distinguish mail,time,name
            else:
                # handle
                # filename lib/grit.rb
                # summary add Blob
                # <and rest>
                if firstpart.startswith('filename'):
                    info['filename'] = parts[-1]
                elif firstpart.startswith('summary'):
                    info['summary'] = parts[-1]
                elif firstpart.startswith('boundary'):
                    info['boundary'] = True
                elif firstpart == '':
                    if info:
                        sha = info['id']
                        c = commits.get(sha)
                        if c is None:
                            if info.get('boundary'):
                                commits[sha] = False
                            else:
                                c = repo.CommitCls(
                                    repo,
                                    hex_to_bin(sha),
                                    author=Actor._from_string(info['author'] + ' ' + info['author_email']),
                                    authored_date=info['author_date'],
                                    committer=Actor._from_string(info['committer'] + ' ' + info['committer_email']),
                                    committed_date=info['committer_date'],
                                    message=info['summary']
                                )
                                commits[sha] = c
                        if c is not False:
                            # END if commit objects needs initial creation
                            m = repo.re_tab_full_line.search(line)
                            text,  = m.groups()
                            blames[-1][0] = c
                            blames[-1][1].append(text)
                        info = { 'id' : sha }
                    # END if we collected commit info
                # END distinguish filename,summary,rest
            # END distinguish author|committer vs filename,summary,rest
        # END distinguish hexsha vs other information

    for commit, lines in blames:
        if commit is not None:
            yield commit, lines

def ignore_file(file):
    for ignore in ALL_IGNORE_FILENAMES:
        if ignore in file['filename']:
            return True

    if file['status'] != 'added':
        return False

    for ignore in ADD_IGNORE_FILENAMES:
        if ignore in file['filename']:
            return True

    return False

def print_stats(stats, level):
    for author, count in sorted(stats.iteritems(), key=operator.itemgetter(1), reverse=True):
        if author in IGNORE_AUTHORS:
            continue

        if isinstance(count, float):
            print "%s%s %.2f" % (' ' * level, author, count)
        else:
            print "%s%s %s" % (' ' * level, author, count)

def correct_scores(stats):
    stats = stats.copy()
    for author in WINNING_TEAM:
        stats[author] = stats.get(author, 0) + WINNING_TEAM_SCORE
    for author in SCORE_CORRECTIONS_DICT.keys():
        stats[author] = stats.get(author, 0)
    stats = {author: count + SCORE_CORRECTIONS_DICT.get(author, 0) for author, count in stats.items()}
    return stats

def print_percents(stats):
    stats = correct_scores(stats)

    stats = {author: float(count) / float(MAX_SCORE) * 100.0 for author, count in stats.items()}

    print_stats(stats, 0)

def print_chart(stats):
    corrected_scores = correct_scores(stats).items()

    labels = []
    values = []

    for author, count in sorted(corrected_scores, key=operator.itemgetter(1), reverse=True):
        if author in IGNORE_AUTHORS:
            continue

        random.seed(author)
        author = author.replace('@', '.')
        c = 0
        while c < 4:
            i = random.randrange(len(author))
            if author[i] != '.':
                author = list(author)
                author[i] = '.'
                author = ''.join(author)
                c += 1
        labels.append(author)
        values.append(count)

    repositories = []
    for github_repository, local_repository in REPOSITORIES:
        local_repository = os.path.abspath(os.path.join(os.path.dirname(__file__), local_repository))
        repo = git.Repo(local_repository)
        repositories.append('%s@%.10s' % (github_repository, repo.heads.master.commit.hexsha))

    args = {
        'cht': 'bhs',
        'chd': 't:%s' % ','.join([str(float(v) / float(MAX_SCORE) * 100.0) for v in values]),
        'chxl': '|'.join(reversed(labels + ['1:'])),
        'chs': '600x500',
        'chbh': 'a',
        'chds': '0,100',
        'chxt': 'x,y',
        'chm': 'N,000000,0,,10',
        'chem': 'y;s=text_outline;po=%f,0.99;d=000000,10,r,ffffff,_,%s' % (1.0 - (0.03 * len(repositories)), ','.join(repositories)),
    }

    print "https://chart.googleapis.com/chart?%s" % urllib.urlencode(args)

global_stats = {}

for github_repository, local_repository in REPOSITORIES:
    print github_repository

    local_repository = os.path.abspath(os.path.join(os.path.dirname(__file__), local_repository))

    pull_requests = github_api('https://api.github.com/repos/%s/pulls' % github_repository, {'state': 'closed'})
    pull_requests = filter(lambda p: p['merged_at'], pull_requests)

    repo = git.Repo(local_repository)
    repo.remotes.origin.fetch()

    for pull in pull_requests:
        number = pull['number']

        if '%s/pull/%d' % (github_repository, number) in IGNORE_PULL_REQUESTS:
            continue

        print "  %s" % pull['html_url']

        pull = json.load(urllib.urlopen('https://api.github.com/repos/%s/pulls/%d' % (github_repository, number)))

        local_stats = {}

        files = github_api('https://api.github.com/repos/%s/pulls/%d/files' % (github_repository, number))
        commits = github_api('https://api.github.com/repos/%s/pulls/%d/commits' % (github_repository, number))

        first_commit = commits[0]['sha']
        last_commit = commits[-1]['sha']
        all_commits = {commit['sha'] for commit in commits}

        for file in files:
            if ignore_file(file):
                continue

            if file['status'] == 'removed':
                continue

            if 'patch' not in file:
                continue

            filename = file['filename']
            print "      %s" % filename

            blames = blame(repo, first_commit, last_commit, filename)

            for commit, lines in blames:
                if commit.hexsha not in all_commits:
                    continue

                author = commit.author.email
                author = MERGE_AUTHORS.get(author, author)
                local_stats[author] = local_stats.get(author, 0) + len(lines)

        all_blamed_authors = set(local_stats.keys())
        all_commits_authors = {commit['commit']['author']['email'] for commit in commits}
        all_commits_authors = {MERGE_AUTHORS.get(author, author) for author in all_commits_authors}

        assert all_blamed_authors <= all_commits_authors, (all_blamed_authors, all_commits_authors)

        print_stats(local_stats, 4)

        for author, count in local_stats.items():
            global_stats[author] = global_stats.get(author, 0) + count

print '======'
print_stats(global_stats, 0)
print '======'
print_percents(global_stats)
print '======'
print_chart(global_stats)
