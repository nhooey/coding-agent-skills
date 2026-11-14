{
  description = "coding-agent-fan-out-headless: Coding-agent skill — run one prompt across many git checkouts, one headless Claude Code session per checkout with its own skills and Nix environment";

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
