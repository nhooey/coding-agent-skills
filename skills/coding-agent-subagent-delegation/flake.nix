{
  description = "coding-agent-subagent-delegation: Coding-agent skill — the main session keeps the conversation, decisions and approvals and delegates nearly all other work to subagents and forks, briefed with fixed sentences about blocked commands, on each agent's model and effort, under one coordinator with a ledger and per-agent worktrees";

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
      skillName = "coding-agent-subagent-delegation";
      src = ./.;
    };
}
