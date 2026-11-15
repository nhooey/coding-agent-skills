{
  description = "coding-agent-session-build-limits: Coding-agent skill — a SessionStart hook that gives every Claude Code session a fixed share of the machine for make, cargo, pytest and the JVM";

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
      skillName = "coding-agent-session-build-limits";
      src = ./.;
    };
}
