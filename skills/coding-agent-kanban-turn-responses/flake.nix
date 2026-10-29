{
  description = "coding-agent-kanban-turn-responses: Coding-agent skill — shape every response as kanban lists: one-line progress updates between tool calls, and a final response of Done/Unfinished/Waiting/Answers/Review/Todo/Decisions lists with an outstanding roll-up";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    agent-skill-flake.url = "github:nhooey/agent-skill-flake";
    agent-skill-flake.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { nixpkgs, agent-skill-flake, ... }:
    agent-skill-flake.lib.mkSkillFlake {
      inherit nixpkgs;
      source = import ../../source.nix;
      skillName = "coding-agent-kanban-turn-responses";
      src = ./.;
      # Ship the reference pages SKILL.md links (examples.md, commands.md,
      # scripts.md); by default only SKILL.md, references/ and scripts/ are
      # installed. Lower-case names only, so README.md stays in the repo.
      extraFiles = [ "[a-z]*.md" ];
    };
}
