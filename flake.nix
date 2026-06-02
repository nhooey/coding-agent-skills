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

    # The git / GitHub skills this repo dogfoods, pulled from the published
    # skills-git marketplace flake (this repo doesn't author them). Installed
    # into the dev shell under its own `agent-skills-all` ownership.
    skills-git = {
      url = "github:nhooey/skills-git";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        flake-skills.follows = "flake-skills";
        treefmt-nix.follows = "treefmt-nix";
      };
    };

    # Skills installed only for authoring this repo (nix-*, humanizer,
    # skill-creator, superpowers), in their own flake so readers don't
    # confuse them with the skills this flake outputs. See
    # ./skills-authoring/flake.nix.
    skills-authoring = {
      url = "path:./skills-authoring";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        flake-skills.follows = "flake-skills";
      };
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
        skillsDir = ./skills;
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
          packages = base.packages.${system};
          apps = base.apps.${system};

          # `nix fmt` runs nixfmt over every tracked `.nix` file; the module
          # also surfaces a `checks.${system}.treefmt` so `nix flake check`
          # fails on unformatted Nix. The repo is Nix-only today — add
          # per-language formatters here as other tracked file types arrive.
          treefmt = {
            projectRootFile = "flake.nix";
            programs.nixfmt.enable = true;
          };

          # Auto-reconcile skills at project scope on `nix develop`: the git
          # skills from the skills-git input and the authoring-only tools from
          # the separate skills-authoring flake, each in its own named startup
          # hook (mirroring skills-git). Both are declarative + idempotent and
          # own disjoint reconcile appNames (git = `agent-skills-all`,
          # authoring = `coding-agent-skills-authoring`), so they coexist in
          # one scope — each sweeps only its own strays.
          devshells.default = {
            name = "coding-agent-skills";
            motd = ''
              {bold}{14}🚀 Entering coding-agent-skills dev shell{reset}
              Run {bold}menu{reset} to list available commands.
            '';
            devshell.startup.install-git-skills.text = ''
              ${inputs.skills-git.apps.${system}.reconcile.program} --scope=project
            '';
            devshell.startup.install-authoring-skills.text = ''
              ${inputs.skills-authoring.reconcileScript system}
            '';
          };
        };
    };
}
