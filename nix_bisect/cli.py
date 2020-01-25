"""Simple command line interface for common use cases"""

import argparse
from nix_bisect import nix, git, git_bisect


def _perform_bisect(attrname, to_pick, max_rebuilds, failure_line, build_options):
    def _quit(result, reason):
        print(f"Quit hook: {result} because of {reason}.")

    git_bisect.register_quit_hook(_quit)

    for rev in to_pick:
        git.try_cherry_pick(rev)

    drv = nix.instantiate(attrname)
    print(f"Instantiated {drv}.")

    if max_rebuilds is not None:
        num_rebuilds = len(nix.build_dry([drv])[0])
        if num_rebuilds > max_rebuilds:
            print(
                f"Need to rebuild {num_rebuilds} derivations, which exceeds the maximum."
            )
            git_bisect.quit_skip()

    try:
        nix.build(nix.dependencies([drv]), build_options)
    except nix.BuildFailure:
        print("Dependencies failed to build.")
        git_bisect.quit_skip()

    if (
        failure_line is not None
        and len(nix.build_dry([drv])[0]) > 0  # needs rebuild
        and nix.log(drv) is not None  # has log
        and failure_line in nix.log(drv)
    ):
        print("Cached failure.")
        git_bisect.quit_bad()

    try:
        _build_result = nix.build([drv], build_options)
    except nix.BuildFailure:
        print(f"Failed to build {attrname}.")
        if failure_line is None or failure_line in nix.log(drv):
            git_bisect.quit_bad()
        else:
            git_bisect.quit_skip()

    if failure_line is not None and failure_line in nix.log(drv):
        git_bisect.quit_bad()
    else:
        git_bisect.quit_good()


def _main():
    parser = argparse.ArgumentParser(
        description="Check the truth of statements against a corpus."
    )
    parser.add_argument(
        "attrname", type=str, help="Name of the attr to build",
    )
    parser.add_argument(
        "--try-cherry-pick",
        action="append",
        default=[],
        help="Cherry pick a commit before building (only if it applies without issues).",
    )
    parser.add_argument(
        "--max-rebuilds",
        type=int,
        help="Skip when a certain rebuild count is exceeded.",
        default=None,
    )
    parser.add_argument(
        "--failure-line",
        help="Whether to try to detect cached failures with a failure line.",
        default=None,
    )
    parser.add_argument(
        "--build-option",
        help="Options to pass through to `nix build` via the `--option` flag.",
        action="append",
        nargs=2,
        default=[],
    )

    try:
        args = parser.parse_args()
    except SystemExit:
        git_bisect.abort()

    build_options = [tuple(option) for option in args.build_option]
    with git.git_checkpoint():
        _perform_bisect(
            args.attrname,
            args.try_cherry_pick,
            args.max_rebuilds,
            args.failure_line,
            build_options,
        )


if __name__ == "__main__":
    _main()
