{
  description = "coding-agent-use-existing-libraries-and-tools: Coding-agent skill — before writing new logic, use the built-ins of the tool already in use, a nixpkgs application or a library through Nix, and write custom code only when none fits";

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
      skillName = "coding-agent-use-existing-libraries-and-tools";
      src = ./.;
    };
}
