import json, operator, os, random, re, urllib

import git

GIT_PATH = None
REPOSITORIES = ()
IGNORE_FILENAMES = ()
IGNORE_AUTHORS = ()
MAX_SCORE = 700
SCORE_CORRECTIONS = {}
WINNING_TEAM_SCORE = 70
WINNING_TEAM = ()

import local_settings

GIT_PATH = getattr(local_settings, 'GIT_PATH', GIT_PATH)
REPOSITORIES += getattr(local_settings, 'REPOSITORIES', ())
IGNORE_FILENAMES += getattr(local_settings, 'IGNORE_FILENAMES', ())
IGNORE_AUTHORS += getattr(local_settings, 'IGNORE_AUTHORS', ())
MAX_SCORE = getattr(local_settings, 'MAX_SCORE', MAX_SCORE)
SCORE_CORRECTIONS.update(getattr(local_settings, 'SCORE_CORRECTIONS', {}))
WINNING_TEAM_SCORE = getattr(local_settings, 'WINNING_TEAM_SCORE', WINNING_TEAM_SCORE)
WINNING_TEAM += getattr(local_settings, 'WINNING_TEAM', ())

if GIT_PATH is not None:
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

def print_chart(stats):
    stats = stats.copy()
    for author in WINNING_TEAM:
        stats[author] = stats.get(author, 0) + WINNING_TEAM_SCORE
    corrected_scores = [(author, count + SCORE_CORRECTIONS.get(author, 0)) for author, count in stats.items()]

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
        print "  %s" % pull['html_url']

        number = pull['number']
        pull = json.load(urllib.urlopen('https://api.github.com/repos/%s/pulls/%d' % (github_repository, number)))

        local_stats = {}

        files = github_api('https://api.github.com/repos/%s/pulls/%d/files' % (github_repository, number))

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
            print "      %s" % filename

            patch = file['patch']

            added_lines = parse_patch(patch)

            assert len(added_lines) == file['additions']

            blamed_lines = blame_lines(repo, filename)

            for line in added_lines:
                author = blamed_lines[line - 1].author.email
                local_stats[author] = local_stats.get(author, 0) + 1

        print_stats(local_stats, 4)

        for author, count in local_stats.items():
            global_stats[author] = global_stats.get(author, 0) + count
            additions += count

        assert additions == pull['additions']

print_stats(global_stats, 0)
print_chart(global_stats)
