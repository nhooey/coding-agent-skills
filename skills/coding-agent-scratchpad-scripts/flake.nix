{
  description = "coding-agent-scratchpad-scripts: Coding-agent skill — edit with the edit tools, run one-off checks inline, never source a generated file, and keep only named data in the scratchpad";

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
      skillName = "coding-agent-scratchpad-scripts";
      src = ./.;
    };
}
