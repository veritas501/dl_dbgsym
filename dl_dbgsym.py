#!/usr/bin/env python3

import requests
import re
import os
import sys
from typing import Text, Optional, Tuple
import shutil
import tempfile


class Log:
    @staticmethod
    def info(s):
        return print(f"[\x1b[1;36m*\x1b[0m] {s}")

    @staticmethod
    def success(s):
        return print(f"[\x1b[1;32m√\x1b[0m] {s}")

    @staticmethod
    def fail(s):
        return print(f"[\x1b[1;31m×\x1b[0m] {s}")

    @staticmethod
    def underline(s):
        return f"\x1b[4m{s}\x1b[0m"


class LibcEnv:
    def __init__(self, libc_filepath: Text) -> None:
        if not os.path.exists(libc_filepath):
            raise IOError('libc file "{}" not exist'.format(libc_filepath))
        self.libc_filepath = libc_filepath
        temp_dir = tempfile.mkdtemp(prefix="dl_dbgsym")
        Log.info("set temp workdir: {}".format(Log.underline(temp_dir)))
        self.workdir = temp_dir

    # main function
    @staticmethod
    def make_env(libc_filepath) -> int:
        return 0 if LibcEnv(libc_filepath).run() else 1

    def run(self) -> bool:
        # get libc basic info
        arch = self.arch
        if not arch:
            return False
        Log.info("find libc arch: {}".format(Log.underline(arch)))
        version = self.version
        if not version:
            return False
        Log.info("find libc version: {}".format(Log.underline(version)))
        build_id = self.get_build_id(self.libc_filepath)
        if not build_id:
            return False
        Log.info("find libc build_id: {}".format(Log.underline(build_id)))
        ubuntu_dist = self.get_ubuntu_dist(version)
        if not ubuntu_dist:
            return False
        Log.info("find ubuntu dist: {}".format(Log.underline(ubuntu_dist)))

        amd64_ver_i386 = False
        libc_dbg_url = self.get_libc_dbg_url(ubuntu_dist, arch, version)
        if not libc_dbg_url:
            return False
        Log.info("find libc-dbg.deb url: {}".format(Log.underline(libc_dbg_url)))
        dbgsym_filepath = self.download_and_extract_debug_symbol(libc_dbg_url, build_id)
        if not dbgsym_filepath:
            if arch == "i386":
                Log.info("try to fetch amd64 build version of libc6-i386-dbgsym")
                libc_dbg_url = self.get_libc_bin_url_i386_amd64(ubuntu_dist, version)
                if not libc_dbg_url:
                    return False
                Log.info(
                    "find libc-dbg.deb url: {}".format(Log.underline(libc_dbg_url))
                )
                dbgsym_filepath = self.download_and_extract_debug_symbol(
                    libc_dbg_url, build_id
                )
                if not dbgsym_filepath:
                    return False
                else:
                    amd64_ver_i386 = True
            else:
                return False

        if not self.move_dbgysm(dbgsym_filepath, build_id):
            return False

        # download ld.so and libc.so
        if amd64_ver_i386:
            libc_bin_url = self.get_libc_bin_url_i386_amd64(ubuntu_dist, version)
        else:
            libc_bin_url = self.get_libc_bin_url(ubuntu_dist, arch, version)
        Log.info("find libc-bin url: {}".format(Log.underline(libc_bin_url)))
        ld_filepath, libc_filepath = self.download_and_extract_ld_and_libc(libc_bin_url)
        os.system(
            'cp "{}" "{}"'.format(
                ld_filepath, os.path.join(os.getcwd(), "ld-{}.so".format(version))
            )
        )
        os.system(
            'cp "{}" "{}"'.format(
                libc_filepath, os.path.join(os.getcwd(), "libc-{}.so".format(version))
            )
        )

        Log.info("done, cleaning ...")
        self.clean()
        return True

    def clean(self):
        os.system('rm -rf "{}"'.format(self.workdir))

    def chk_cmd(self, command) -> bool:
        return shutil.which(command) is not None

    def chk_cmds(self, commands) -> bool:
        return all(map(self.chk_cmd, commands))

    def check_cmd(self, command) -> None:
        if not self.chk_cmd(command):
            raise OSError('command "{}" not found'.format(command))

    def check_cmds(self, commands) -> None:
        for cmd in commands:
            self.check_cmd(cmd)

    @property
    def version(self) -> Optional[Text]:
        self.check_cmds(["strings", "grep"])
        data = os.popen(
            'strings "{}" | grep "GNU C Library"'.format(self.libc_filepath)
        ).read()
        try:
            ver = re.search(r"GLIBC (.*?)\)", data).group(1)
        except:  # noqa: E722
            Log.fail("can't find ubuntu glibc version")
            return None

        return ver

    @property
    def arch(self) -> Optional[Text]:
        self.check_cmds(["readelf"])
        data = os.popen('readelf -h "{}"'.format(self.libc_filepath)).read()
        if "X86-64" in data:
            return "amd64"
        elif "80386" in data:
            return "i386"
        elif "ARM" in data:
            return "armhf"
        elif "AArch64" in data:
            return "arm64"
        elif "PowerPC64" in data:
            return "ppc64el"
        elif "IBM S/390" in data:
            return "s390x"
        else:
            Log.fail("unsupported arch")
            return None

    def get_build_id(self, filename) -> Optional[Text]:
        self.check_cmds(["readelf"])
        data = os.popen(
            'readelf --notes "{}" 2>/dev/null | grep "Build ID"'.format(filename)
        ).read()
        try:
            build_id = re.search(r"Build ID: (\w+)", data).group(1)
        except:  # noqa: E722
            Log.fail("can't find glibc build_id")
            return None

        return build_id

    def get_ubuntu_dist(self, version) -> Optional[Text]:
        url = "https://launchpad.net/ubuntu/+source/glibc/{}".format(version)
        r = requests.get(url)
        try:
            dist = re.search(r'<a href="/ubuntu/(\w+)">', r.text).group(1)
        except:  # noqa: E722
            Log.fail("can't find ubuntu dist")
            return None

        return dist

    def get_libc_dbg_url(self, dist, arch, version) -> Optional[Text]:
        url = "https://launchpad.net/ubuntu/{}/{}/libc6-dbg/{}".format(
            dist, arch, version
        )
        r = requests.get(url)
        try:
            dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
        except:  # noqa: E722
            Log.fail("can't find libc-dbg download url")
            return None

        return dl_url

    def get_libc_dbgsym_url_i386_amd64(self, dist, version) -> Optional[Text]:
        url = "https://launchpad.net/ubuntu/{}/amd64/libc6-i386-dbgsym/{}".format(
            dist, version
        )
        r = requests.get(url)
        try:
            dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
        except:  # noqa: E722
            Log.fail("can't find libc-dbg download url")
            return None

        return dl_url

    def get_libc_bin_url(self, dist, arch, version) -> Optional[Text]:
        url = "https://launchpad.net/ubuntu/{}/{}/libc6/{}".format(dist, arch, version)
        r = requests.get(url)
        try:
            dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
        except:  # noqa: E722
            Log.fail("can't find libc download url")
            return None

        return dl_url

    def get_libc_bin_url_i386_amd64(self, dist, version) -> Optional[Text]:
        url = "https://launchpad.net/ubuntu/{}/amd64/libc6-i386/{}".format(
            dist, version
        )
        r = requests.get(url)
        try:
            dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
        except:  # noqa: E722
            Log.fail("can't find libc download url")
            return None

        return dl_url

    def may_sudo(self, command) -> Text:
        if os.geteuid() != 0 and not command.startswith("sudo"):
            return "sudo {}".format(command)
        return command

    def move_dbgysm(self, filename, buildid) -> bool:
        self.check_cmds(["mkdir", "cp"])
        base_path = "/usr/lib/debug/.build-id"
        target_dir = os.path.join(base_path, buildid[:2])
        target_name = os.path.join(target_dir, "{}.debug".format(buildid[2:]))

        Log.info(f"moving dbgsym to {Log.underline(target_name)}")
        os.system(self.may_sudo("mkdir -p {}".format(target_dir)))
        os.system(self.may_sudo("cp {} {}".format(filename, target_name)))

        recheck_buildid = self.get_build_id(target_name)
        if recheck_buildid != buildid:
            Log.fail("move dbgsym fail")
            return False
        else:
            Log.success("move dbgsym done!!")
            return True

    def download(self, url, dst_filepath) -> bool:
        self.check_cmd("wget")
        Log.info(
            "download {} to {}".format(Log.underline(url), Log.underline(dst_filepath))
        )
        return os.system('wget "{}" -O "{}"'.format(url, dst_filepath)) == 0

    def get_target_pkg_name_in_deb(self, deb_filepath) -> Text:
        self.check_cmd("ar")
        data = os.popen('ar -t "{}" | grep data'.format(deb_filepath)).read()
        data = data.strip("\r\n\t ")
        file_list = data.splitlines()
        if len(file_list) > 1:
            raise Exception("multi target pkg found in deb: {}".format(file_list))
        if len(file_list) < 1:
            raise Exception("no target pkg found in deb")
        return file_list[0].strip("\r\n\t ")

    def extract_pkg_in_deb(self, deb_filepath, target_pkg, output_dir):
        self.check_cmds(["ar", "tar"])

        target_pkg_filepath = os.path.join(self.workdir, target_pkg)
        res = os.system(
            'ar -x --output "{}" "{}" "{}"'.format(
                self.workdir, deb_filepath, target_pkg
            )
        )
        if res:
            raise Exception("use ar to extract pkg failed")

        if target_pkg.endswith(".zst"):
            self.check_cmds(["unzstd"])
            res = os.system(
                'tar --zstd -xf "{}" -C "{}"'.format(target_pkg_filepath, output_dir)
            )
        else:
            res = os.system(
                'tar -xf "{}" -C "{}"'.format(target_pkg_filepath, output_dir)
            )
        if res:
            raise Exception("use tar to extract pkg failed")

    def download_and_extract_debug_symbol(self, url, target_build_id) -> Optional[Text]:
        self.check_cmds(["rm", "mkdir", "find", "grep"])
        target_filename = "libc6-dbg.deb"
        target_filepath = os.path.join(self.workdir, target_filename)
        if os.path.exists(target_filepath):
            os.remove(target_filepath)

        # download deb
        if not self.download(url, target_filepath):
            raise Exception("download deb file failed")

        # extract deb
        target_pkg = self.get_target_pkg_name_in_deb(target_filepath)
        Log.info("extract {} ...".format(target_pkg))
        target_extract_path = os.path.join(self.workdir, "libc6-dbg")
        if os.path.exists(target_extract_path):
            os.system('rm -rf "{}"'.format(target_extract_path))
        os.system('mkdir -p "{}"'.format(target_extract_path))
        self.extract_pkg_in_deb(target_filepath, target_pkg, target_extract_path)

        # find target dbgsym
        find_result = (
            os.popen(
                'find {} -type f \( -name "libc-*.so" -or -name "{}.debug" \) -exec file {{}} + | grep "ELF" | awk -F: \'{{print $1}}\' | grep -v prof'.format(
                    target_extract_path, target_build_id[2:]
                )
                if self.chk_cmds(["file", "awk"])
                else 'find {} -type f \( -name "libc-*.so" -or -name "{}.debug" \) | grep -v prof'.format(
                    target_extract_path, target_build_id[2:]
                )
            )
            .read()
            .strip()
        )
        dbgsym_filepaths = [x.strip("\r\n\t ") for x in find_result.splitlines()]
        for dbgsym_filepath in dbgsym_filepaths:
            Log.info(
                "found candidate: {}, checking ...".format(
                    Log.underline(dbgsym_filepath)
                )
            )
            dbgsym_build_id = self.get_build_id(dbgsym_filepath)
            if dbgsym_build_id == target_build_id:
                Log.success("build id match, found target dbgsym!!")
                return dbgsym_filepath

        # not found, return None
        Log.fail("no corresponding dbgsym file found")
        return None

    def download_and_extract_ld_and_libc(self, url) -> Tuple[Text]:
        self.check_cmds(["rm", "mkdir", "find", "grep"])
        target_filename = "libc6-bin.deb"
        target_filepath = os.path.join(self.workdir, target_filename)
        if os.path.exists(target_filepath):
            os.remove(target_filepath)

        # download deb
        if not self.download(url, target_filepath):
            raise Exception("download deb file failed")

        # extract deb
        target_pkg = self.get_target_pkg_name_in_deb(target_filepath)
        Log.info("extract {} ...".format(target_pkg))
        target_extract_path = os.path.join(self.workdir, "libc6-bin")
        if os.path.exists(target_extract_path):
            os.system('rm -rf "{}"'.format(target_extract_path))
        os.system('mkdir -p "{}"'.format(target_extract_path))
        self.extract_pkg_in_deb(target_filepath, target_pkg, target_extract_path)

        # find target ld
        find_result = (
            os.popen(
                'find {} -type f -name "ld*.so*" -exec file {{}} + | grep "ELF" | awk -F: \'{{print $1}}\' | grep -v prof'.format(
                    target_extract_path
                )
                if self.chk_cmds(["file", "awk"])
                else 'find {} -type f -name "ld*.so*" | grep -v prof'.format(
                    target_extract_path
                )
            )
            .read()
            .strip()
        )
        ld_filepaths = [x.strip("\r\n\t ") for x in find_result.splitlines()]
        if len(ld_filepaths) > 1:
            raise Exception(
                "multi target ld.so result found in deb: {}".format(ld_filepaths)
            )
        elif len(ld_filepaths) < 1:
            raise Exception("no target ld.so found in deb")
        else:
            Log.success("find ld.so: {}".format(Log.underline(ld_filepaths[0])))

        # find libc
        find_result = (
            os.popen(
                'find {} -type f \\( -name "libc*.so" -or -name "libc*.so.6" \\) -exec file {{}} + | grep "ELF" | awk -F: \'{{print $1}}\' | grep -v prof'.format(
                    target_extract_path
                )
                if self.chk_cmds(["file", "awk"])
                else 'find {} -type f \\( -name "libc*.so" -or -name "libc*.so.6" \\) | grep -v prof'.format(
                    target_extract_path
                )
            )
            .read()
            .strip()
        )
        libc_filepaths = [x.strip("\r\n\t ") for x in find_result.splitlines()]
        libc_filepaths = [
            libc_filepath
            for libc_filepath in libc_filepaths
            if self.get_build_id(libc_filepath) == self.get_build_id(self.libc_filepath)
        ]
        if len(libc_filepaths) > 1:
            raise Exception(
                "multi target libc.so result found in deb: {}".format(libc_filepaths)
            )
        elif len(libc_filepaths) < 1:
            raise Exception("no target libc.so found in deb")
        else:
            Log.success("find libc.so: {}".format(Log.underline(libc_filepaths[0])))

        return ld_filepaths[0], libc_filepaths[0]


def main(argv) -> int:
    if len(argv) == 1:
        print("Download libc dbgsym and corresponding ld.so")
        print(f"Usage: python3 {argv[0]} <target libc.so>")
        return 1

    target_libc_so = argv[1]
    return LibcEnv.make_env(target_libc_so)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
