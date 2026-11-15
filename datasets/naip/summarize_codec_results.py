#!/usr/bin/env python3
"""Markdown tables and pass-mark verdicts for the codec comparison, for VALIDATION.md.

    python3 summarize_codec_results.py <folder> <quad name> [<quad name> ...]

Reads <quad>.json (jxl_test.py), <quad>-codecs.json (codec_test.py) and <quad>-level-bytes.json
(bytes stored at each level of every GeoTIFF build). Every verdict is worked out here from the
rules in VALIDATION.md, not typed.
"""
import json
import sys


def meets(build, bar, colour_bar):
    return all(a >= b for a, b in zip(build["psnr_db_by_level"][0], bar)) and build["colour_psnr_db"] >= colour_bar


def main():
    folder, quads = sys.argv[1], sys.argv[2:]
    for quad in quads:
        with open(f"{folder}/{quad}.json") as f:
            first = json.load(f)["builds"]
        with open(f"{folder}/{quad}-codecs.json") as f:
            second = json.load(f)
        with open(f"{folder}/{quad}-level-bytes.json") as f:
            level_bytes = json.load(f)
        builds = {**first, **second["builds"]}
        jpeg, full = builds["jpeg-65-75"], builds["jpeg-65-75-full-colour"]
        bar, colour_bar, size = jpeg["psnr_db_by_level"][0], full["colour_psnr_db"], jpeg["file_bytes"]
        views = {**{k[len(quad) + 1:-4]: v for k, v in second["views_of_existing_files"].items()},
                 **{k: v["views"] for k, v in second["builds"].items() if "views" in v}}
        print(f"\n**{quad}** ({second['megapixels']} megapixels; published JPEG {size / 1e6:.1f} MB, of which "
              f"{level_bytes['jpeg-65-75'][0] / 1e6:.1f} MB is the full-resolution level)\n")
        print("| Build | File | Against published | PSNR R, G, B | Colour PSNR | Encode CPU s | Decode CPU s | "
              "Street view: requests, KB | Whole quad at 1:16: requests, KB |")
        print("|---|---|---|---|---|---|---|---|---|")
        for name, b in builds.items():
            if "file_bytes" not in b:
                print(f"| {name} | failed: {b.get('failed', '')[:60]} | | | | | | | |")
                continue
            v = views.get(name)
            print("| " + " | ".join([
                name, f"{b['file_bytes'] / 1e6:.1f} MB", f"{b['file_bytes'] / size - 1:+.0%}",
                ", ".join(f"{x:.1f}" for x in b["psnr_db_by_level"][0]), f"{b['colour_psnr_db']:.1f}",
                str(b.get("encode_cpu_s", "")), str(b["decode_all_levels_cpu_s"]),
                f"{v['street_1024_px_window']['requests']}, {v['street_1024_px_window']['bytes'] / 1e3:,.0f}" if v else "",
                f"{v['whole_quad_at_one_sixteenth']['requests']}, {v['whole_quad_at_one_sixteenth']['bytes'] / 1e3:,.0f}" if v else "",
            ]) + " |")

        def smallest(prefix, against=size):
            ok = sorted((b["file_bytes"], n) for n, b in builds.items()
                        if n.startswith(prefix) and "ovr" not in n and "-e" not in n and "file_bytes" in b and meets(b, bar, colour_bar))
            if not ok:
                return "FAILED: no build tested meets the error and colour bars"
            saving = 1 - ok[0][0] / against
            return f"{'passed' if saving >= 0.15 else 'FAILED'}: {ok[0][1]} is the smallest that meets both bars, {-saving:+.0%}"

        print(f"\nBars: PSNR {bar} in every band (published JPEG) and colour-only PSNR {colour_bar} (full-colour JPEG).\n")
        print(f"- JPEG XL mark 1: {smallest('jxl-d')}")
        cog = all(first[n]["layout"] == "COG" and first[n]["block"] == [512, 512] and first[n]["overviews"] == 5 for n in first if n.startswith("jxl"))
        print(f"- JPEG XL mark 2 (COG, 512 px blocks, five levels): {'passed' if cog else 'FAILED'}")
        for label, prefix in (("JPEG 2000", "jp2-q"), ("HTJ2K", "htj2k-s")):
            print(f"- {label} mark 1: {smallest(prefix)}")
            mine = [views[n] for n in views if n.startswith(prefix)]
            limit = 2 * views["jpeg-65-75"]["whole_quad_at_one_sixteenth"]["bytes"]
            ok = all(v["street_1024_px_window"]["requests"] <= 10 and v["whole_quad_at_one_sixteenth"]["requests"] <= 10
                     and v["whole_quad_at_one_sixteenth"]["bytes"] <= limit for v in mine)
            wide = [v["whole_quad_at_one_sixteenth"] for v in mine]
            print(f"- {label} mark 2 (views by range request): {'passed' if ok else 'FAILED'}: the whole-quad view took "
                  f"{min(w['requests'] for w in wide)} to {max(w['requests'] for w in wide)} requests and "
                  f"{min(w['bytes'] for w in wide) / 1e6:.1f} to {max(w['bytes'] for w in wide) / 1e6:.1f} MB, "
                  f"against {views['jpeg-65-75']['whole_quad_at_one_sixteenth']['bytes'] / 1e6:.2f} MB for the published JPEG")
        print(f"- AVIF mark 3 (against the published JPEG's full-resolution level): {smallest('avif-', level_bytes['jpeg-65-75'][0])}")
        verdicts = []
        for name, b in builds.items():
            if "ovr" in name and "file_bytes" in b:
                every = all(a >= c for got, want in zip(b["psnr_db_by_level"], jpeg["psnr_db_by_level"]) for a, c in zip(got, want))
                saving = 1 - b["file_bytes"] / size
                verdicts.append(f"{name} {-saving:+.0%}, every level at least the published JPEG's: {'yes' if every else 'no'}"
                                f" ({'passes' if every and saving >= 0.15 else 'fails'})")
        print(f"- JPEG XL with finer overviews, mark 4: {'; '.join(verdicts)}")


if __name__ == "__main__":
    main()
