from __future__ import absolute_import
from lintreview.diff import parse_diff, Diff, DiffCollection
from lintreview.fixers.commit_strategy import CommitStrategy
from lintreview.fixers.error import ConfigurationError
import lintreview.git as git
import logging

log = logging.getLogger(__name__)


workflow_strategies = {
    'commit': CommitStrategy
}


def create_context(review_config, app_config, repo_path,
                   head_repository, pull_request):
    """Create the context used for running fixers"""
    context = {
        'strategy': review_config.fixer_workflow(),
        'enabled': review_config.fixers_enabled(),
        'author_name': app_config['GITHUB_AUTHOR_NAME'],
        'author_email': app_config['GITHUB_AUTHOR_EMAIL'],
        'repo_path': repo_path,
        'pull_request': pull_request,
        'repository': head_repository,
    }
    return context


def run_fixers(tools, base_path, files):
    """Run fixer mode of each tool on each file
    Return a DiffCollection based on the parsed diff
    from the fixer changes.

    If no diff is generated an empty list will be returned"""
    log.info('Running fixers on %d files', len(files))

    for tool in tools:
        if tool.has_fixer():
            tool.execute_fixer(files)
    diff = git.diff(base_path, files)
    if diff:
        return parse_diff(diff)
    return []


def find_intersecting_diffs(original, fixed):
    intersection = []
    if not original or not fixed:
        return intersection

    for name in fixed.get_files():
        original_diff = original.all_changes(name)
        if not len(original_diff):
            log.debug('No matching original diff for %s', name)
            continue
        fixed_diff = fixed.all_changes(name)[0]
        hunks = fixed_diff.intersection(original_diff[0])
        intersection.append(Diff(None, name, '00000', hunks=hunks))
    return intersection


def apply_fixer_diff(original_diffs, fixer_diff, strategy_context):
    """Apply the relevant changes from fixer_diff

    Using the original_diff and fixer_diff, find the intersecting
    changes and delegate to the requested workflow strategy
    to apply and commit the changes.
    """
    if 'strategy' not in strategy_context:
        raise ConfigurationError('Missing `workflow` configuration.')

    strategy = strategy_context['strategy']
    if strategy not in workflow_strategies:
        raise ConfigurationError(u'Unknown workflow `{}`'.format(strategy))

    try:
        log.info('Using %s workflow to apply fixer changes', strategy)
        workflow = workflow_strategies[strategy](strategy_context)
    except Exception as e:
        msg = u'Could not create {} workflow. Got {}'.format(strategy, e)
        raise ConfigurationError(msg)

    changes_to_apply = find_intersecting_diffs(original_diffs, fixer_diff)
    workflow.execute(changes_to_apply)


def add_strategy(name, implementation):
    """Add a workflow strategy
    Used by different hosting environments to add new workflows
    """
    log.info('Adding %s fixer strategy', name)
    workflow_strategies[name] = implementation


def rollback_changes(path):
    git.reset_hard(path)
