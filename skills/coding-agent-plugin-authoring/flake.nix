{
  description = "coding-agent-plugin-authoring: Coding-agent skill — lay out, build, test and ship a Claude Code plugin with agent-plugins-nixpkgs' claudePlugin flake module";

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
      skillName = "coding-agent-plugin-authoring";
      src = ./.;
    };
}
