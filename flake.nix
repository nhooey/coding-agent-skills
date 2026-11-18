{
  description = "coding-agent-skills: Coding agent skills marketplace as a Nix flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    # Declared explicitly even though `agent-skill-flake` already pulls in
    # `treefmt-nix` transitively: this flake owns its formatter toolchain
    # rather than borrowing a dependency's. The consumer below `follows` this
    # input so the whole tree resolves to one version.
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # `agent-skill-flake` is the builder library, not a skill — it turns skill
    # directories into installable flakes and aggregates them, and exports the
    # `flakeModules.devshellSkills` flake-parts module that wires the dev shell
    # below (motd + install-skills startup + the ci/dev/maintenance command
    # trio + the reap-skills/update-skills-devshell pair). That module bundles
    # numtide/devshell, so this flake needs no `devshell` input of its own. It
    # carries zero skill inputs, so keeping it here does not drag the skill mesh
    # into the root lock; the dev-shell skill sources live only in the
    # `skills-devshell/` sub-flake's lock and are invoked at RUNTIME.
    agent-skill-flake = {
      url = "github:nhooey/agent-skill-flake";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        treefmt-nix.follows = "treefmt-nix";
      };
    };
  };

  outputs =
    {
      nixpkgs,
      flake-parts,
      agent-skill-flake,
      ...
    }@inputs:
    let
      # The skills this repo outputs: every skill under ./skills built into
      # per-skill packages plus the base install/preview apps. The dev-shell
      # skill set is NOT an output here — it lives in the `skills-devshell/`
      # sub-flake and is invoked at runtime by the dev shell below.
      base = agent-skill-flake.lib.mkAllSkillsFlake {
        inherit nixpkgs;
        source = import ./source.nix;
        skillsDir = ./skills;
        packagePrefix = "agent-skill-";
        # Ship the reference pages a SKILL.md links beside it (examples.md,
        # commands.md, ...); by default only SKILL.md, references/ and
        # scripts/ are installed. Lower-case names only, so a skill's
        # README.md stays in the repo for people instead of being installed.
        extraFiles = [ "[a-z]*.md" ];
        # Name the aggregate by owner+topic (agent-skills-nhooey-coding-agent-all)
        # rather than the owner-wide `agent-skills-nhooey-all`. The owner-wide
        # key would collide across all repos this owner publishes under
        # skillspkgs / nur-packages' last-write-wins `//` merge; the
        # owner+topic name is resolvable and unique, mirroring git-skills's
        # `agent-skills-nhooey-git-all`. The aggregate carries the home-manager
        # `isFlakeSkillsEnv` passthru itself, so `default` is directly
        # installable.
        name = "agent-skills-nhooey-coding-agent-all";
      };
    in
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = import inputs.systems;
      imports = [
        # Bundles numtide/devshell + the whole dev-shell skills convention
        # (motd, install-skills startup, the ci/dev/maintenance command trio,
        # and the reap-skills/update-skills-devshell pair). Configured via the
        # `agent-skill-flake.devshellSkills` options block below. The dev-shell
        # skill set (the git/GitHub pack plus skillspkgs' `authoring`
        # combination) is defined in the runtime `skills-devshell/` sub-flake
        # and invoked at RUNTIME, never as a root input, so this repo keeps zero
        # skill inputs in its own lock.
        inputs.agent-skill-flake.flakeModules.devshellSkills
        inputs.treefmt-nix.flakeModule
      ];

      # Keep coding-agent-skills' custom banner; the module's generated motd is
      # overridden by passing `motd` here.
      agent-skill-flake.devshellSkills = {
        name = "coding-agent-skills";
        motd = ''
          {bold}{14}🚀 Entering coding-agent-skills dev shell{reset}
          Run {bold}menu{reset} to list available commands.
        '';
      };
      perSystem =
        {
          config,
          system,
          pkgs,
          ...
        }:
        let
          inherit (pkgs) lib;

          # The Python the tests run under: the skills' scripts use only the
          # standard library, and the tests may use these libraries too.
          testPython = pkgs.python3.withPackages (ps: [ ps.pytest ]);

          # `skill-tests [python | shell | SKILL ...]`: each language's tests
          # with its own tool, pytest for test_*.py and bash for each test_*.sh,
          # under tests/ and scripts/; or only one language's; or only the
          # named skills' under tests/. A selection that runs no test fails.
          # `skills-dev test` and the python-tests and shell-tests checks all
          # run it.
          skillTests = pkgs.writeShellApplication {
            name = "skill-tests";
            runtimeInputs = [
              testPython
              pkgs.bash
              pkgs.git
            ];
            text = ''
              cd "''${PRJ_ROOT:-$PWD}"
              language=
              folders=(tests scripts)
              if [ $# -eq 1 ] && { [ "$1" = python ] || [ "$1" = shell ]; }; then
                language=$1
              elif [ $# -gt 0 ]; then
                folders=()
                for skill in "$@"; do
                  case $skill in
                    python | shell) echo "skill-tests: $skill is a language, which goes alone" >&2; exit 2 ;;
                    "" | . | .. | */*) echo "skill-tests: $skill: not a skill" >&2; exit 2 ;;
                  esac
                  if [ ! -d "skills/$skill" ] || [ ! -d "tests/$skill" ]; then
                    echo "skill-tests: $skill: no skills/$skill with tests in tests/$skill" >&2
                    exit 2
                  fi
                  folders+=("tests/$skill")
                done
              fi
              python_tests=()
              shell_tests=()
              if [ "$language" != shell ]; then
                mapfile -t python_tests < <(find "''${folders[@]}" -name 'test_*.py' | sort)
              fi
              if [ "$language" != python ]; then
                mapfile -t shell_tests < <(find "''${folders[@]}" -name 'test_*.sh' | sort)
              fi
              if [ $((''${#python_tests[@]} + ''${#shell_tests[@]})) -eq 0 ]; then
                echo "skill-tests: no ''${language:+$language }tests in ''${folders[*]}" >&2
                exit 1
              fi
              status=0
              if [ ''${#python_tests[@]} -gt 0 ]; then
                pytest "''${python_tests[@]}" || status=1
              fi
              for test in "''${shell_tests[@]}"; do
                echo "==== $test"
                bash "$test" </dev/null || status=1
              done
              exit "$status"
            '';
          };

          # One check per language, running `skill-tests <language>` on a
          # writable copy of the skills, the dev tools and their tests.
          testCheck =
            language:
            pkgs.runCommand "${language}-tests" { } ''
              cp -r ${
                lib.fileset.toSource {
                  root = ./.;
                  fileset = lib.fileset.unions [
                    ./pytest.ini
                    ./scripts
                    ./skills
                    ./tests
                  ];
                }
              } $TMPDIR/src
              chmod -R u+w $TMPDIR/src
              export HOME=$TMPDIR PRJ_ROOT=$TMPDIR/src
              ${lib.getExe skillTests} ${language}
              touch $out
            '';
        in
        {
          # The skills, and the hooks plugin `coding-agent-skills-hooks`: plugin/
          # with each hook script copied in from its skill. A skill adds a hook
          # by listing its script here and running it from plugin/hooks/hooks.json.
          packages = base.packages.${system} // {
            hooks-plugin = import ./nix/hooks-plugin.nix {
              inherit pkgs;
              src = ./plugin;
              hookScripts = [
                ./skills/coding-agent-session-build-limits/scripts/session-build-limits.sh
                ./skills/coding-agent-scratchpad-scripts/scripts/scratchpad-guard.sh
                ./skills/coding-agent-scratchpad-scripts/scripts/scratchpad_guard.py
                ./skills/coding-agent-plans-as-graph/scripts/plans-check-hook.sh
                ./skills/coding-agent-plans-as-graph/scripts/plans_check_hook.py
                ./skills/coding-agent-plans-as-graph/scripts/plans.py
                ./skills/coding-agent-route-feedback-to-skills-over-memory/scripts/memory-write-reminder.sh
                ./skills/coding-agent-route-feedback-to-skills-over-memory/scripts/memory_write_reminder.py
                ./skills/coding-agent-browser-selection/scripts/browser-check-hook.sh
                ./skills/coding-agent-browser-selection/scripts/browser_check_hook.py
                ./skills/coding-agent-kanban-turn-responses/scripts/reply-lint-hook.sh
                ./skills/coding-agent-kanban-turn-responses/scripts/reply_lint_hook.py
                ./skills/coding-agent-kanban-turn-responses/scripts/lint_reply.py
                ./skills/coding-agent-kanban-turn-responses/scripts/reply_turns.py
              ];
            };
          };

          # The built hooks plugin's manifest, hooks.json and scripts. The
          # checker's own tests run in python-tests.
          checks.hooks-plugin =
            pkgs.runCommand "hooks-plugin-check"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.bash
                ];
              }
              ''
                python3 -I ${./scripts}/check_hooks_plugin.py ${config.packages.hooks-plugin}
                touch $out
              '';

          apps = base.apps.${system};

          # Every test: pytest over the Python tests under tests/ and scripts/,
          # the layout test and the dev tools' own tests among them, and bash
          # over each shell test.
          checks.python-tests = testCheck "python";
          checks.shell-tests = testCheck "shell";

          # The review queue's ordering, chunking, input checks and edges, with
          # no gh or browser: `bb test` in the skill's tests, on its scripts and
          # its SKILL.md.
          checks.review-queue-in-browser =
            pkgs.runCommand "review-queue-in-browser-tests" { nativeBuildInputs = [ pkgs.babashka ]; }
              "cd ${
                lib.fileset.toSource {
                  root = ./.;
                  fileset = lib.fileset.unions [
                    ./skills/coding-agent-review-queue-in-browser/SKILL.md
                    ./skills/coding-agent-review-queue-in-browser/scripts
                    ./tests/coding-agent-review-queue-in-browser
                  ];
                }
              }/tests/coding-agent-review-queue-in-browser && bb test && touch $out";

          # `nix fmt` runs nixfmt over `.nix` and prettier over `.md` / `.yaml`;
          # the module also surfaces a `checks.${system}.treefmt` so `nix flake
          # check` fails on any unformatted file. prettier's includes are pinned
          # to markdown and YAML so it leaves `evals.json` (and any future JSON)
          # alone — add formatters here as other tracked file types arrive.
          treefmt = {
            projectRootFile = "flake.nix";
            programs.nixfmt.enable = true;
            programs.prettier.enable = true;
            settings.formatter.prettier.includes = [
              "*.md"
              "*.yaml"
              "*.yml"
            ];
            # prettier trims trailing spaces even inside fenced code blocks,
            # and the kanban skill's examples need them: each list header there
            # ends in 2 spaces, the hard break the skill itself requires. Its
            # README's example has the same headers.
            settings.formatter.prettier.excludes = [
              "skills/coding-agent-kanban-turn-responses/examples.md"
              "skills/coding-agent-kanban-turn-responses/README.md"
            ];
          };

          # The devshellSkills module (imported above) supplies this devShell's
          # name, motd, the install-skills startup that reconciles the runtime
          # `skills-devshell/` sub-flake at project scope, the ci/dev/maintenance
          # command trio (check / fmt / update-flake), and the skills commands
          # (reap-skills / update-skills-devshell). This repo adds `skills-dev`:
          # `skills-dev test` runs skill-tests, as the python-tests and
          # shell-tests checks do, and the rest goes to scripts/skills_dev.py,
          # whose `mods check` needs `claude` itself and the Claude Code API
          # types its running build writes, neither of which the Nix sandbox
          # has, so it runs here rather than in `nix flake check`.
          devshells.default = {
            packages = [
              testPython
              pkgs.typescript
            ];
            commands = [
              {
                category = "dev";
                name = "skills-dev";
                help = "test [python|shell|SKILL]: run the tests under tests/; mods check|try: check or try the mods under plugins/";
                command = ''
                  if [ "''${1-}" = test ]; then
                    shift
                    exec ${lib.getExe skillTests} "$@"
                  fi
                  exec python3 "$PRJ_ROOT/scripts/skills_dev.py" "$@"
                '';
              }
            ];
          };
        };
    };
}
