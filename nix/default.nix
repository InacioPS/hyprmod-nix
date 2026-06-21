{
  lib,
  python3Packages,
  fetchFromGitHub,
  wrapGAppsHook4,
  glib,
  gtk4,
  libadwaita,
  gobject-introspection,
  lua,
}:

let
  inherit (python3Packages) buildPythonApplication buildPythonPackage
    fetchPypi pygobject3 hatchling;

  hyprland-config = buildPythonPackage rec {
    pname = "hyprland-config";
    version = "0.9.9";
    src = fetchPypi {
      pname = "hyprland_config";
      inherit version;
      sha256 = "bab524f2afbd64f178fdd93a15e116be2d7490b603c93827de2f024082507f14";
    };
    pyproject = true;
    nativeBuildInputs = [ hatchling ];
  };

  hyprland-schema = buildPythonPackage rec {
    pname = "hyprland-schema";
    version = "0.6.3";
    src = fetchPypi {
      pname = "hyprland_schema";
      inherit version;
      sha256 = "e5a46fac1aeabbadc0a3c9fcfc1ec4bcea405eec9b670cb3960fbd6420666ad0";
    };
    pyproject = true;
    nativeBuildInputs = [ hatchling ];
  };

  hyprland-socket = buildPythonPackage rec {
    pname = "hyprland-socket";
    version = "0.12.2";
    src = fetchPypi {
      pname = "hyprland_socket";
      inherit version;
      sha256 = "b45778940710d0667d372f227bc53452fdf123d71d1dcbd652a97677ecbfc70b";
    };
    pyproject = true;
    nativeBuildInputs = [ hatchling ];
  };

  hyprland-monitors = buildPythonPackage rec {
    pname = "hyprland-monitors";
    version = "0.8.0";
    src = fetchPypi {
      pname = "hyprland_monitors";
      inherit version;
      sha256 = "fd4b75f9163aa30c2e73d9c49d98f4f159ee1485b45eb2fcf345ac387f9efa46";
    };
    pyproject = true;
    nativeBuildInputs = [ hatchling ];
    propagatedBuildInputs = [ hyprland-socket ];
  };

  hyprland-state = buildPythonPackage rec {
    pname = "hyprland-state";
    version = "0.4.2";
    src = fetchPypi {
      pname = "hyprland_state";
      inherit version;
      sha256 = "6b3f1553abca10a75f5a5f9d2f53d33704f1cebb557e2138bd41abbd58612e89";
    };
    pyproject = true;
    nativeBuildInputs = [ hatchling ];
    propagatedBuildInputs = [ hyprland-config hyprland-socket hyprland-schema hyprland-monitors ];
  };
in

buildPythonApplication rec {
  pname = "hyprmod";
  version = "0.3.0";

  src = lib.cleanSource ../.;

  pyproject = true;

  nativeBuildInputs = [ wrapGAppsHook4 glib hatchling gobject-introspection ];
  buildInputs = [ gtk4 libadwaita gobject-introspection lua ];

  propagatedBuildInputs = [
    pygobject3
    hyprland-config
    hyprland-schema
    hyprland-socket
    hyprland-state
    hyprland-monitors
  ];

  postInstall = ''
    mkdir -p $out/share
    cp -r data/* $out/share/
  '';

  meta = {
    description = "Native GTK4/libadwaita settings app for Hyprland";
    homepage = "https://github.com/BlueManCZ/hyprmod";
    license = lib.licenses.gpl3Only;
    mainProgram = "hyprmod";
    platforms = lib.platforms.linux;
  };
}
