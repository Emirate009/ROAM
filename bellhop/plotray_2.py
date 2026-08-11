import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


def plotray(filename):
    Nsxyz = np.zeros(3, dtype=int)
    NBeamAngles = np.zeros(2, dtype=int)

    filename = Path(filename)

    if not filename.exists():
        raise FileNotFoundError(f"Ray file not found: {filename.resolve()}")

    with filename.open("r") as fid:
        title = fid.readline().strip()
        freq = float(fid.readline())

        datai = fid.readline().split()
        Nsxyz[0] = int(datai[0])
        Nsxyz[1] = int(datai[1])
        Nsxyz[2] = int(datai[2])

        datai = fid.readline().split()
        NBeamAngles[0] = int(datai[0])
        NBeamAngles[1] = int(datai[1])

        depth_top = float(fid.readline())
        depth_bottom = float(fid.readline())
        ray_type = fid.readline().strip()

        nsx = Nsxyz[0]
        nsy = Nsxyz[1]
        nsz = Nsxyz[2]

        nalpha = NBeamAngles[0]
        nbeta = NBeamAngles[1]

        print(f"Title: {title}")
        print(f"Frequency: {freq} Hz")
        print(f"Source counts: {nsx}, {nsy}, {nsz}")
        print(f"Beam angles: {nalpha}, {nbeta}")
        print(f"Depth range: {depth_top} to {depth_bottom}")
        print(f"Ray type: {ray_type}")

        rmin = np.inf
        rmax = -np.inf
        zmin = np.inf
        zmax = -np.inf

        fig, ax = plt.subplots(figsize=(10, 6))

        rays_plotted = 0

        for isz in range(nsz):
            for ibeam in range(nalpha):
                angle_line = fid.readline()

                if not angle_line:
                    print(
                        f"Reached end of file at source {isz}, "
                        f"beam {ibeam}."
                    )
                    break

                angle_line = angle_line.strip()

                if not angle_line:
                    continue

                alpha0 = float(angle_line)

                step_line = fid.readline()
                if not step_line:
                    break

                datai = step_line.split()

                nsteps = int(datai[0])
                num_top_bounces = int(datai[1])
                num_bottom_bounces = int(datai[2])

                r = np.zeros(nsteps)
                z = np.zeros(nsteps)

                for j in range(nsteps):
                    ray_line = fid.readline()

                    if not ray_line:
                        raise EOFError(
                            f"Unexpected end of file while reading "
                            f"beam {ibeam}, step {j}."
                        )

                    rz = ray_line.split()
                    r[j] = float(rz[0])
                    z[j] = float(rz[1])

                if nsteps > 0:
                    rmin = min(rmin, np.min(r))
                    rmax = max(rmax, np.max(r))
                    zmin = min(zmin, np.min(z))
                    zmax = max(zmax, np.max(z))

                    ax.plot(r, -z)
                    rays_plotted += 1

        if rays_plotted == 0:
            raise RuntimeError("The file was read, but no rays were plotted.")

        ax.set_xlim(rmin, rmax)
        ax.set_ylim(-zmax, -zmin)

        ax.set_title(title)
        ax.set_xlabel("Range")
        ax.set_ylabel("Depth")
        ax.grid(True)

        plt.tight_layout()
        plt.show()


def main():
    script_directory = Path(__file__).resolve().parent
    fname = script_directory / "WG_.ray"

    plotray(fname)


if __name__ == "__main__":
    main()