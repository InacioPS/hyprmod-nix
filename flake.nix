{
  description = "HyprMod - Native GTK4/libadwaita settings app for Hyprland";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        hyprmod = pkgs.callPackage ./nix/default.nix { };
      in {
        packages.default = hyprmod;
        devShells.default = pkgs.mkShell {
          inputsFrom = [ hyprmod ];
          packages = [
            pkgs.python3Packages.hatchling
            pkgs.python3Packages.pyright
            pkgs.python3Packages.pytest
            pkgs.python3Packages.ruff
          ];
        };
      }
    );
}
