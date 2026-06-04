{
  description = "coding-agent-skills: Coding agent skills marketplace as a Nix flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    devshell = {
      url = "github:numtide/devshell";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # Declared explicitly even though `skills-git` and `flake-skills` already
    # pull in `treefmt-nix` transitively: this flake owns its formatter
    # toolchain rather than borrowing a dependency's. Both consumers below
    # `follows` this input so the whole tree resolves to one version.
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # `flake-skills` is the builder library, not a skill — it turns skill
    # directories into installable flakes and aggregates them.
    flake-skills = {
      url = "github:nhooey/flake-skills";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        treefmt-nix.follows = "treefmt-nix";
      };
    };

    # ---------------------------------------------------------------------
    # Dev-shell skill sources (inlined — consumed only by `devshells` below)
    # ---------------------------------------------------------------------
    # The project dev shell installs one curated skill set: the git/GitHub
    # pack plus skillspkgs' `authoring` combination — combined via
    # flake-skills' `mkCombination` in `outputs` (`devshellSkills`). These
    # were previously isolated in a `skills-devshell/` sub-flake, but a
    # same-repo sub-flake can only be addressed by a relative `path:` input
    # (which sandboxed/transitive consumers reject) or a brittle self-URL
    # (which breaks on any repo/owner/host rename), so they are inlined here
    # instead. They follow the parent `nixpkgs` but NOT `flake-skills`: the
    # root pins a newer owner-namespacing `flake-skills`, and forcing the
    # `authoring` combination's transitive sources onto it surfaces an
    # ownerless aggregate-key the strict namespace check rejects. Letting each
    # source keep its own (compatible) `flake-skills` matches how the old
    # sub-flake's isolated lock worked. `mkCombination` still runs from the
    # root's `flake-skills.lib`, so the combiner is this repo's pinned rev.

    skills-git = {
      url = "github:nhooey/skills-git";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # skillspkgs' curated `authoring` combination, surfaced through its own
    # subdir flake (`mkCombination` keeps a combination re-composable). This
    # is a `?dir=` into a *different* repo, which fetches cleanly for
    # transitive consumers — unlike a self-referential `?dir=`.
    skillspkgs-combinations = {
      url = "github:nhooey/skillspkgs?dir=sources/combinations";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      nixpkgs,
      flake-parts,
      flake-skills,
      ...
    }@inputs:
    let
      # The skills this repo outputs: every skill under ./skills built into
      # per-skill packages plus the base install/preview apps. The git and
      # authoring skills consumed below are *inputs*, not outputs — see the
      # `skills-git` and `skills-authoring` inputs.
      base = flake-skills.lib.mkAllSkillsFlake {
        inherit nixpkgs;
        source = import ./source.nix;
        skillsDir = ./skills;
        packagePrefix = "agent-skill-";
      };

      packs = {
        # Every coding-agent-* skill as one env. mkAllSkillsFlake already
        # exposes the same set under the auto `agent-skills-all` key, but that
        # name collides across sibling repos when aggregated (skillspkgs /
        # nur-packages do a last-write-wins `//` merge), so the bare key is
        # unreachable downstream. This uniquely-named pack — mirroring
        # skills-git's `agent-skills-git-all` and skills-nix's
        # `agent-skills-nix-all` — survives the merge. Keep in sync as skills
        # are added.
        agent-skills-coding-agent-all = [
          "coding-agent-keep-computer-awake"
          "coding-agent-questions-as-first-class-prompts"
          "coding-agent-route-feedback-to-skills-over-memory"
          "coding-agent-session-recap"
        ];
      };

      # Build a `flake-skills.lib.mkSkillsEnv` for one (packName, skillNames)
      # pair. The env keeps the same `nix run`/`nix build` UX as a plain
      # `symlinkJoin`, but also carries the `passthru.isFlakeSkillsEnv` +
      # `flakeSkillsEnv` records that `programs.flake-skills.skills` needs to
      # expand the env back into per-skill records on home-manager activation.
      mkEnv =
        system: packName: skillNames:
        flake-skills.lib.mkSkillsEnv {
          pkgs = nixpkgs.legacyPackages.${system};
          name = packName;
          skills = builtins.map (n: base.bySkillName.${system}.${n}) skillNames;
        };

      # The project dev-shell skill set, combined from the inlined skill
      # sources (the git/GitHub pack plus skillspkgs' `authoring`
      # combination). `reconcileScript` is a `system -> string` function the
      # dev shell splices into a startup hook.
      devshellSkills = flake-skills.lib.mkCombination {
        inherit nixpkgs;
        name = "coding-agent-skills-devshell";
        envName = "agent-skills-coding-agent-skills-devshell";
        packagePrefix = "agent-skill-";
        sources = [
          { source = inputs.skills-git; }
          { source = inputs.skillspkgs-combinations.combinations.authoring; }
        ];
      };
    in
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = import inputs.systems;
      imports = [
        inputs.devshell.flakeModule
        inputs.treefmt-nix.flakeModule
      ];
      perSystem =
        { system, ... }:
        {
          packages =
            base.packages.${system}
            // builtins.mapAttrs (packName: skillNames: mkEnv system packName skillNames) packs;

          apps = base.apps.${system};

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
          };

          # Auto-reconcile the dev-shell skill set (git/GitHub + the authoring
          # combination) at project scope on `nix develop`. `devshellSkills`
          # (above) yields the reconcile one-liner per system; this just
          # splices it in.
          devshells.default = {
            name = "coding-agent-skills";
            motd = ''
              {bold}{14}🚀 Entering coding-agent-skills dev shell{reset}
              Run {bold}menu{reset} to list available commands.
            '';
            devshell.startup.install-skills.text = ''
              ${devshellSkills.reconcileScript system}
            '';
          };
        };
    };
}
