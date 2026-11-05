{
  description = "coding-agent-vpn-blocked-domains: Coding-agent skill — when a domain blocks a request, suggest excluding it from the VPN if the traffic went through one, or connecting the VPN if it didn't";

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
      skillName = "coding-agent-vpn-blocked-domains";
      src = ./.;
    };
}
