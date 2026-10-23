#!/usr/bin/env python3
import subprocess
import sys
import os

def signing_args():
    """apksigner keystore arguments for the bundled public keystore."""
    return [
        "--ks", "keystore/public.jks",
        "--ks-pass", "pass:public",
        "--key-pass", "pass:public",
        "--ks-key-alias", "public",
    ]

def fix_apk(apk_path):
    """Try to fix APK using apktool"""
    try:
        # Decode and rebuild
        subprocess.run([
            "apktool", "d", apk_path, "-o", "temp_decoded",
            "--force", "--no-src"
        ], check=True, capture_output=True)
        
        # Rebuild
        subprocess.run([
            "apktool", "b", "temp_decoded", "-o", "fixed.apk"
        ], check=True, capture_output=True)
        
        return "fixed.apk"
    except Exception:
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_and_sign.py <input.apk> [output.apk]")
        sys.exit(1)
    
    input_apk = sys.argv[1]
    output_apk = sys.argv[2] if len(sys.argv) > 2 else "signed-" + os.path.basename(input_apk)
    
    # Try to fix first
    fixed = fix_apk(input_apk)
    
    # Sign with apksigner
    if fixed:
        subprocess.run([
            "apksigner", "sign",
            *signing_args(),
            "--in", fixed,
            "--out", output_apk
        ], check=True)
        print(f"✅ Fixed and signed: {output_apk}")
    else:
        # Just try to sign normally
        try:
            subprocess.run([
                "apksigner", "sign",
                *signing_args(),
                "--in", input_apk,
                "--out", output_apk
            ], check=True)
            print(f"✅ Signed: {output_apk}")
        except Exception:
            print(f"❌ Failed to sign {input_apk}")

if __name__ == "__main__":
    main()
