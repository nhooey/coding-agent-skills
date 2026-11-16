{
  description = "coding-agent-route-feedback-to-skills-over-memory: Coding-agent skill — when the user gives behavioral feedback, route it to the layer that owns it (a skill or preferences edit, or a plan node for a hook, tool or config) before falling back to auto-memory";

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
      skillName = "coding-agent-route-feedback-to-skills-over-memory";
      src = ./.;
    };
}
