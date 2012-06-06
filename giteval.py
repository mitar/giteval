import json, operator, os, re, urllib

import git

GITHUB_REPOSITORY = 'wlanslovenija/PiplMesh'
LOCAL_REPOSITORY = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'PiplMesh'))
GIT_PATH = '/opt/local/bin'
IGNORE_FILENAMES = (
    'jQuery_library_1_7_1.js',
    'COPYING',
    'LICENSE',
    'static/piplmesh/jquery/',
)
IGNORE_AUTHORS = (
    'mitar.git@tnode.com',
)

os.environ['PATH'] += ':%s' % GIT_PATH

PAGE_SIZE = 100
PATCH_HEADER = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

def github_api(url, args={}):
    data = []

    page = 1
    while True:
        args.update({
            'per_page': PAGE_SIZE,
            'page': page,
        })
        d = json.load(urllib.urlopen("%s?%s" % (url, urllib.urlencode(args))))
        data.extend(d)

        if len(d) < PAGE_SIZE:
            break
        else:
            page += 1

    return data

def parse_patch(patch):
    add_lines = []

    line_number = None
    for line in patch.splitlines():
        if line.startswith('@'):
            line_number = int(PATCH_HEADER.match(line).group(3))
        elif line.startswith('-'):
            pass
        elif line.startswith('\\'):
            pass
        elif line.startswith('+'):
            add_lines.append(line_number)
            line_number += 1
        else:
            assert line.startswith(' ')
            line_number += 1

    return add_lines

def blame_lines(repo, filename):
    blame = repo.blame(file['sha'], filename)

    blamed_lines = []

    for change, lines in blame:
        for line in lines:
            blamed_lines.append(change)

    return blamed_lines

def ignore_file(file):
    if file['status'] != 'added':
        return False

    for ignore in IGNORE_FILENAMES:
        if ignore in file['filename']:
            return True

    return False

def print_stats(stats, level):
    for author, count in sorted(stats.iteritems(), key=operator.itemgetter(1), reverse=True):
        if author in IGNORE_AUTHORS:
            continue

        print "%s%s %s" % (' ' * level, author, count)

pull_requests = github_api('https://api.github.com/repos/%s/pulls' % GITHUB_REPOSITORY, {'state': 'closed'})
pull_requests = filter(lambda p: p['merged_at'], pull_requests)

repo = git.Repo(LOCAL_REPOSITORY)
repo.remotes.origin.fetch()

global_stats = {}

for pull in pull_requests:
    print pull['html_url']

    number = pull['number']
    pull = json.load(urllib.urlopen('https://api.github.com/repos/%s/pulls/%d' % (GITHUB_REPOSITORY, number)))

    local_stats = {}

    files = github_api('https://api.github.com/repos/%s/pulls/%d/files' % (GITHUB_REPOSITORY, number))

    additions = 0

    for file in files:
        assert file['sha'] == pull['head']['sha']

        if ignore_file(file):
            additions += file['additions']
            continue

        if file['status'] == 'removed':
            continue

        if 'patch' not in file:
            continue

        filename = file['filename']
        print "    %s" % filename

        patch = file['patch']

        added_lines = parse_patch(patch)

        assert len(added_lines) == file['additions']

        blamed_lines = blame_lines(repo, filename)

        for line in added_lines:
            author = blamed_lines[line - 1].author.email
            local_stats[author] = local_stats.get(author, 0) + 1

    print_stats(local_stats, 2)

    for author, count in local_stats.items():
        global_stats[author] = global_stats.get(author, 0) + count
        additions += count

    assert additions == pull['additions']

print_stats(global_stats, 0)
