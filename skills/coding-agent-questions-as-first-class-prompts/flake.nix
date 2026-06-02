{
  description = "coding-agent-questions-as-first-class-prompts: Coding-agent skill — pose every user-facing question through the agent's first-class question facility, never as prose, with `All`/`None` as the first two options of any multi-select";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-skills.url = "github:nhooey/flake-skills";
    flake-skills.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { nixpkgs, flake-skills, ... }:
    flake-skills.lib.mkSkillFlake {
      inherit nixpkgs;
      skillName = "coding-agent-questions-as-first-class-prompts";
      src = ./.;
    };
}
