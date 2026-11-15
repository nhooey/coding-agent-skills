{
  description = "coding-agent-skills dev-shell skill set — an isolated sub-flake invoked at RUNTIME by the root devShell, never a root input. The skill sources live only in THIS flake's lock, so the root coding-agent-skills stays a leaf with zero skill inputs and transitive consumers never drag the skill mesh in.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";

    # The builder lib. agent-skill-flake carries zero skill inputs, so it does
    # not drag the skill mesh into this sub-flake's lock — only the skill
    # sources below do.
    agent-skill-flake = {
      url = "github:nhooey/agent-skill-flake";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Dev-shell skill sources. They follow the parent `nixpkgs` but NOT
    # `agent-skill-flake`: forcing skillspkgs' `authoring` combination's
    # transitive sources onto a single pinned builder surfaces an ownerless
    # aggregate-key the strict namespace check rejects, so each source keeps
    # its own (compatible) builder. `mkDevshellSkillsFlake` still runs from this
    # flake's `agent-skill-flake.lib`, so the combiner is the pinned rev above.

    coding-agent-skills = {
      url = "github:nhooey/coding-agent-skills/overnight-skills";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    git-skills = {
      url = "github:nhooey/git-skills/overnight-skills";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-skills = {
      url = "github:nhooey/nix-skills/overnight-skills";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    python-skills = {
      url = "github:nhooey/python-skills/overnight-skills";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    shell-skills = {
      url = "github:nhooey/shell-skills/overnight-skills";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # skillspkgs' curated `authoring` combination, surfaced through its own
    # subdir flake (`mkCombination` keeps a combination re-composable). A
    # `?dir=` into a *different* repo fetches cleanly for transitive consumers.
    # Its skill-repository inputs follow the ones above, so the combination
    # installs the same revisions this flake pins.
    skillspkgs-combinations = {
      url = "github:nhooey/skillspkgs?dir=sources/combinations";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.git-skills.follows = "git-skills";
      inputs.nix-skills.follows = "nix-skills";
    };
  };

  # One `mkDevshellSkillsFlake` call: the dev shell's whole skill set as a
  # single combination, surfaced as runnable apps (reconcile / purge / …).
  outputs =
    {
      nixpkgs,
      agent-skill-flake,
      ...
    }@inputs:
    agent-skill-flake.lib.mkDevshellSkillsFlake {
      inherit nixpkgs;
      systems = import inputs.systems;
      name = "coding-agent-skills-devshell";
      # envName and packagePrefix are left at their library defaults:
      # mkDevshellSkillsFlake derives envName = "agent-skills-${name}"
      # (== agent-skills-coding-agent-skills-devshell) and packagePrefix
      # defaults to "agent-skill-".
      sources = [
        # Commits, branches and pull requests.
        { source = inputs.git-skills; }
        # Safe shell commands: named deletes, PIDs, no machine-wide changes.
        { source = inputs.shell-skills; }
        # The Python scripts the skills here bundle.
        { source = inputs.python-skills; }
        # Running headless sessions, keeping the scratchpad tidy, the plan
        # graph in agents/plans/, and how one skill refers to another.
        {
          source = inputs.coding-agent-skills;
          skills = [
            "coding-agent-headless-in-checkout"
            "coding-agent-plans-as-graph"
            "coding-agent-scratchpad-scripts"
            "coding-agent-skill-references"
          ];
        }
        # Skill authoring: nix-flakes, humanizer, anthropic skill-creator,
        # superpowers.
        { source = inputs.skillspkgs-combinations.combinations.authoring; }
      ];
    };
}
