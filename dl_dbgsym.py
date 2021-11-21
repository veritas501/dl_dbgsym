#!/usr/bin/env python3
import requests
import re
from os import system,popen,chdir
import sys

log_info = lambda s: print(f'[\033[1;36m*\033[0m] {s}')
log_success = lambda s: print(f'[\033[1;32m√\033[0m] {s}')
log_fail = lambda s: print(f'[\033[1;31m×\033[0m] {s}')
underline = lambda s: f'\033[4m{s}\033[0m'

def set_libc_env(filename):
	def get_arch(filename):
		data = popen(f'readelf -h "{filename}"').read()
		if 'X86-64' in data:
			return 'amd64'
		elif '80386' in data:
			return 'i386'
		elif 'ARM' in data:
			return 'armhf'
		elif 'AArch64' in data:
			return 'arm64'
		elif 'PowerPC64' in data:
			return 'ppc64el'
		elif 'IBM S/390' in data:
			return 's390x'
		else:
			log_fail(f'unsupported arch')
			clean()
			exit(1)

	def get_ver(filename):
		data = popen(f'strings "{filename}" | grep "GNU C Library"').read()
		try:
			ver = re.search(r'GLIBC (.*?)\)', data).group(1)
		except:
			log_fail(f'can\'t find ubuntu glibc version')
			clean()
			exit(1)
		return ver

	def get_buildid(filename):
		data = popen(f'readelf --notes "{filename}" | grep "Build ID"').read()
		try:
			buildid = re.search(r'Build ID: (\w+)',data).group(1)
		except:
			log_fail(f'can\'t find glibc buildid')
			clean()
			exit(1)
		return buildid

	def find_dist(ver):
		url = f'https://launchpad.net/ubuntu/+source/glibc/{ver}'
		r = requests.get(url)
		try:
			dist = re.search(r'<a href="/ubuntu/(\w+)">', r.text).group(1)
		except:
			log_fail(f'can\'t find ubuntu dist')
			clean()
			exit(1)
		return dist

	def find_libc_dbg_url(dist,arch,ver):
		url = f'https://launchpad.net/ubuntu/{dist}/{arch}/libc6-dbg/{ver}'
		r = requests.get(url)
		try:
			dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
		except:
			log_fail(f'can\'t find libc-dbg download url')
			clean()
			exit(1)
		return dl_url

	def find_libc_dbgsym_url_i386_amd64(dist,arch,ver):
		url = f'https://launchpad.net/ubuntu/{dist}/amd64/libc6-i386-dbgsym/{ver}'
		r = requests.get(url)
		try:
			dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
		except:
			log_fail(f'can\'t find libc-dbg download url')
			clean()
			exit(1)
		return dl_url

	def find_libc_bin_url(dist,arch,ver):
		url = f'https://launchpad.net/ubuntu/{dist}/{arch}/libc6/{ver}'
		r = requests.get(url)
		try:
			dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
		except:
			log_fail(f'can\'t find libc download url')
			clean()
			exit(1)
		return dl_url

	def find_libc_bin_url_i386_amd64(dist,arch,ver):
		url = f'https://launchpad.net/ubuntu/{dist}/amd64/libc6-i386/{ver}'
		r = requests.get(url)
		try:
			dl_url = re.search(r'<a class="sprite" href="(.*?)">', r.text).group(1)
		except:
			log_fail(f'can\'t find libc download url')
			clean()
			exit(1)
		return dl_url

	def move_dbgysm(filename,buildid):
		target_dir = f'/usr/lib/debug/.build-id/{buildid[:2]}'
		target_name = f'/usr/lib/debug/.build-id/{buildid[:2]}/{buildid[2:]}.debug'
		log_info(f'moving dbgsym to {underline(target_name)}')
		system(f'sudo mkdir -p {target_dir}')
		system(f'sudo cp {filename} {target_name}')
		recheck_buildid = get_buildid(target_name)
		if recheck_buildid != buildid:
			log_fail(f'move dbgsym fail')
			clean()
			exit(1)
		log_success(f'move dbgsym done!!')

	def clean():
		log_info(f'cleaning...')
		system(f'cd ..;rm -rf "{version}_tmp"')

	arch = get_arch(filename)
	log_info(f'find libc arch: {underline(arch)}')
	version = get_ver(filename)
	log_info(f'find libc version: {underline(version)}')
	buildid = get_buildid(filename)
	log_info(f'find libc buildid: {underline(buildid)}')
	dist = find_dist(version)
	log_info(f'find ubuntu dist: {underline(dist)}')
	system(f'rm -rf "{version}_tmp"')
	system(f'mkdir -p "{version}_tmp"')
	chdir(f'{version}_tmp')
	# set dbgsym
	amd64_ver_i386 = False
	libc_dbg_url = find_libc_dbg_url(dist,arch,version)
	log_info(f'find libc-dbg url: {underline(libc_dbg_url)}')
	system(f'wget {libc_dbg_url} -O libc6-dbg.deb')
	system(f'ar -x libc6-dbg.deb data.tar.xz')
	system(f'mkdir -p libc6-dbg')
	system(f'tar -xf data.tar.xz -C ./libc6-dbg')
	dbgsym_filename = popen(f'find libc6-dbg -name "libc-*.so" -type f').read().strip()
	dbg_buildid = get_buildid(dbgsym_filename)
	if dbg_buildid != buildid:
		log_fail(f'dbgsym buildid not match: {underline(dbg_buildid)}')
		if arch != 'i386':
			clean()
			exit(1)
		else:
			log_info(f'try to fetch amd64 build version of libc6-i386-dbgsym')
		libc_dbgsym_url = find_libc_dbgsym_url_i386_amd64(dist,arch,version)
		log_info(f'find libc6-i386-dbgsym url: {underline(libc_dbgsym_url)}')
		system(f'wget {libc_dbgsym_url} -O libc6-i386-dbgsym.ddeb')
		system(f'ar -x libc6-i386-dbgsym.ddeb data.tar.xz')
		system(f'mkdir -p libc6-i386-dbgsym')
		system(f'tar -xf data.tar.xz -C ./libc6-i386-dbgsym')
		dbgsym_filename = popen(f'find libc6-i386-dbgsym -name "{buildid[2:]}.debug" -type f | grep -v prof').read().strip()
		dbg_buildid = get_buildid(dbgsym_filename)
		if dbg_buildid != buildid:
			log_fail(f'dbgsym buildid not match: {underline(dbg_buildid)}')
			clean()
			exit(1)
		amd64_ver_i386=True
	log_success(f'find dbgsym!!')
	move_dbgysm(dbgsym_filename,dbg_buildid)
	# download ld.so
	if amd64_ver_i386:
		libc_bin_url = find_libc_bin_url_i386_amd64(dist,arch,version)
	else:
		libc_bin_url = find_libc_bin_url(dist,arch,version)
	log_info(f'find libc-bin url: {underline(libc_bin_url)}')
	system(f'wget {libc_bin_url} -O libc6.deb')
	system(f'ar -x libc6.deb data.tar.xz')
	system(f'mkdir -p libc6')
	system(f'tar -xf data.tar.xz -C ./libc6')
	ld_filename = popen(f'find libc6 -name "ld-*.so" -type f').read().strip()
	log_success(f'find ld.so!!')
	system(f'cp "{ld_filename}" ../')
	clean()

if __name__ == "__main__":
	if len(sys.argv) == 1:
		print('Download libc dbgsym and ld.so')
		print(f'Usage: python3 {sys.argv[0]} <target_libc.so>')
	else:
		set_libc_env(sys.argv[1])
