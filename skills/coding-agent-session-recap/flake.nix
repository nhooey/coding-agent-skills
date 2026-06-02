{
  description = "coding-agent-session-recap: Coding-agent skill — render the current conversation as an alternating 🗣 / 🤖 dialogue script when the user asks for a session recap";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-skills.url = "github:nhooey/flake-skills";
    flake-skills.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { nixpkgs, flake-skills, ... }:
    flake-skills.lib.mkSkillFlake {
      inherit nixpkgs;
      skillName = "coding-agent-session-recap";
      src = ./.;
    };
}
