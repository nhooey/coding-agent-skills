{
  description = "coding-agent-questions-as-first-class-prompts: Coding-agent skill — pose every user-facing question through the agent's first-class question facility, never as prose, with `All`/`None` as the first two options of any multi-select";

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
      skillName = "coding-agent-questions-as-first-class-prompts";
      src = ./.;
    };
}
