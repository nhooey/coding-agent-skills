{
  description = "coding-agent-find-implicit-models: Coding-agent skill — find the lifecycles, sources of truth, protocols, bounds and supervisors a codebase runs without naming them, write them down, and make one explicit only when that deletes code or illegal states";

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
      skillName = "coding-agent-find-implicit-models";
      src = ./.;
    };
}
