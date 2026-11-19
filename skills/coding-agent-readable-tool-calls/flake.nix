{
  description = "coding-agent-readable-tool-calls: Coding-agent skill — make each tool call easy to read in the terminal, with short paths, a description saying what it does and why, and quiet commands";

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
      skillName = "coding-agent-readable-tool-calls";
      src = ./.;
    };
}
