{
  description = "coding-agent-skills dev-shell skill set — an isolated sub-flake invoked at RUNTIME by the root devShell, never a root input. The skill sources live only in THIS flake's lock, so the root coding-agent-skills stays a leaf with zero skill inputs and transitive consumers never drag the skill mesh in.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";

    # The builder lib. agent-skill-flake carries zero skill inputs, so it does
    # not drag the skill mesh into this sub-flake's lock — only the skill
    # source below does.
    agent-skill-flake = {
      url = "github:nhooey/agent-skill-flake";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # skillspkgs' per-family combinations, surfaced through their own subdir
    # flake. It follows this flake's `nixpkgs` but NOT `agent-skill-flake`:
    # forcing the combination's transitive sources onto a single pinned
    # builder surfaces an ownerless aggregate-key the strict namespace check
    # rejects, so it keeps its own (compatible) builder.
    # `mkDevshellSkillsFlake` still runs from this flake's
    # `agent-skill-flake.lib`, so the combiner is the pinned rev above.
    skillspkgs-combinations = {
      url = "github:nhooey/skillspkgs?dir=sources/combinations";
      inputs.nixpkgs.follows = "nixpkgs";
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
        # The skill-collections family's combination, the one skill set every
        # skill collection installs. Nothing is added: the family's
        # combination already covers the Python this repository's skills
        # bundle.
        { source = inputs.skillspkgs-combinations.combinations.skill-collections; }
      ];
    };
}
