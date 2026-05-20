{
  description = "claude-code-session-recap: Claude Code skill — render the current conversation as an alternating 🗣 / 🤖 dialogue script when the user asks for a session recap";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-skills.url = "github:nhooey/flake-skills";
    flake-skills.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { nixpkgs, flake-skills, ... }:
    flake-skills.lib.mkSkillFlake {
      inherit nixpkgs;
      skillName = "claude-code-session-recap";
      src = ./.;
    };
}
