giteval
=======

giteval evaluates GitHub repository and its pull requests. It counts line changes for each
pull request for each author and sums them together. It helps evaluate overall contributions
by each author through time and not just contributions which stayed in the current version.

It outputs counts to the standard output and a Google API chart URL.

Configuration
-------------

You should create a file named `local_settings.py` and define the following variables:

* `GITHUB_ACCESS_TOKEN` -- your [GitHub API access token](https://github.com/settings/applications)
* `GIT_PATH` -- additional path containing `git` executable, added to `PATH` environment variable
* `REPOSITORIES` -- a list of tuples of repositories to evaluate, `('project_name/repository_name', 'path/to/local/clone/of/the/repository')`
* `ADD_IGNORE_FILENAMES` -- a list of all filenames to ignore when they are first added to the repository (for example, you might want to ignore external libraries being added to the repository, but count all local changes to them)
* `ALL_IGNORE_FILENAMES` -- a list of all filenames to always ignore
* `IGNORE_PULL_REQUESTS` -- a list of pull requests to ignore, `'project_name/repository_name/pull/123'`
* `IGNORE_AUTHORS` -- a list of authors to ignore, their e-mail addresses
* `MERGE_AUTHORS` -- a dictionary of mappings between secondary e-mail addresses of authors and their primary e-mail addresses used when evaluating
* `MAX_SCORE` -- scores are normalized to `MAX_SCORE`, default 1000
* `SCORE_CORRECTIONS` -- scores for authors can be manually adjusted by specifying a list of tuples `('author@e-mail.com', 100)`
