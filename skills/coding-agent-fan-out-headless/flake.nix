{
  description = "coding-agent-fan-out-headless: Coding-agent skill — run a prompt as a headless Claude Code session inside one git checkout, with its own skills and Nix environment, and fan it out across many";

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
      skillName = "coding-agent-fan-out-headless";
      src = ./.;
    };
}
