{
  description = "coding-agent-keep-computer-awake: Coding-agent skill — start claffeinate at the start of every prompt to keep the Mac awake during processing";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-skills.url = "github:nhooey/flake-skills";
    flake-skills.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { nixpkgs, flake-skills, ... }:
    flake-skills.lib.mkSkillFlake {
      inherit nixpkgs;
      skillName = "coding-agent-keep-computer-awake";
      src = ./.;
    };
}
