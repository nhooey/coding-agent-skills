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
        # Name the aggregate "all" bundle by topic rather than letting it
        # default to the owner-scoped `agent-skills-nhooey-all`. Every repo
        # this owner publishes would derive that same owner key, so they
        # collide under skillspkgs / nur-packages' last-write-wins `//`
        # merge; the topic-scoped name survives, mirroring git-skills's
        # `agent-skills-git-all`. The aggregate now carries the
        # home-manager `isFlakeSkillsEnv` passthru itself (agent-skill-flake
        # #47), so `default` is directly installable — no hand-rolled pack.
        name = "agent-skills-coding-agent-all";
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
        { system, ... }:
        {
          packages = base.packages.${system};

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

          # The devshellSkills module (imported above) supplies this devShell's
          # name, motd, the install-skills startup that reconciles the runtime
          # `skills-devshell/` sub-flake at project scope, the ci/dev/maintenance
          # command trio (check / fmt / update-flake), and the skills commands
          # (reap-skills / update-skills-devshell). This repo adds no dev-shell
          # packages or commands of its own, so there is no `devshells.default`
          # block here.
        };
    };
}
