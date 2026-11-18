# The repository's hooks plugin: plugin/ with each hook script copied in from
# its skill's scripts/ folder, where the skill documents it.
#
# The same derivation as agent-plugins-nixpkgs' `lib.mkClaudePlugin pkgs { src,
# postPatch }`: name and version from the manifest, `passthru.claudePluginName`
# and `passthru.version` for its `mkMarketplace`. It is built here rather than
# through that library because agent-plugins-nixpkgs takes this flake as an
# input to pass this package through, and an input back would be a cycle.
{
  pkgs,
  # The plugin folder, holding .claude-plugin/plugin.json and hooks/hooks.json.
  src,
  # Hook scripts, each copied to scripts/<its name>, which hooks.json runs as
  # `bash "${CLAUDE_PLUGIN_ROOT}/scripts/<name>"`.
  hookScripts,
}:
let
  inherit (pkgs) lib;
  manifest = lib.importJSON "${src}/.claude-plugin/plugin.json";
in
pkgs.runCommand "claude-plugin-${manifest.name}-${manifest.version}"
  {
    passthru = {
      claudePluginName = manifest.name;
      inherit (manifest) version;
    };
  }
  ''
    cp -r ${src} $out
    chmod -R u+w $out
    mkdir -p $out/scripts
    ${lib.concatMapStrings (script: ''
      cp ${script} $out/scripts/${lib.escapeShellArg (baseNameOf script)}
    '') hookScripts}
  ''
