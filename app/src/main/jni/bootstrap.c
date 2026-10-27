#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/utsname.h>
#include <unistd.h>
#include <elf.h>

#define BLKROSET   0x125d
#define KSUD_STAGE "/data/user_de/0/df.root/ksud"
#define KSUD       "/data/adb/ksud"
#define MODULES_DIR "/data/adb/modules"
#define OPTIONAL_KSU_KO "/data/local/tmp/kernelsu.ko"

static void touch(const char *path) {
    int fd = open(path, O_CREAT | O_WRONLY, 0666);
    if (fd >= 0) close(fd);
}

// verify kernel module vermagic
static int check_vermagic(const char *ko_path) {
    if (!ko_path || access(ko_path, F_OK) != 0) return 0;
    int fd = open(ko_path, O_RDONLY);
    if (fd < 0) return -1;
    Elf64_Ehdr ehdr;
    if (read(fd, &ehdr, sizeof(ehdr)) != sizeof(ehdr)) { close(fd); return -1; }
    if (memcmp(ehdr.e_ident, ELFMAG, SELFMAG) != 0 || ehdr.e_ident[EI_CLASS] != ELFCLASS64) { close(fd); return -1; }
    if (ehdr.e_shentsize != sizeof(Elf64_Shdr) || ehdr.e_shnum == 0) { close(fd); return -1; }
    size_t sh_table_size = (size_t)ehdr.e_shentsize * ehdr.e_shnum;
    Elf64_Shdr *shdrs = malloc(sh_table_size);
    if (!shdrs) { close(fd); return -1; }
    if (lseek64(fd, ehdr.e_shoff, SEEK_SET) < 0 || read(fd, shdrs, sh_table_size) != (ssize_t)sh_table_size) {
        free(shdrs); close(fd); return -1;
    }
    if (ehdr.e_shstrndx >= ehdr.e_shnum) { free(shdrs); close(fd); return -1; }
    size_t strtab_size = shdrs[ehdr.e_shstrndx].sh_size;
    char *shstrtab = malloc(strtab_size);
    if (!shstrtab) { free(shdrs); close(fd); return -1; }
    if (lseek64(fd, shdrs[ehdr.e_shstrndx].sh_offset, SEEK_SET) < 0 || read(fd, shstrtab, strtab_size) != (ssize_t)strtab_size) {
        free(shstrtab); free(shdrs); close(fd); return -1;
    }
    off64_t modinfo_offset = 0;
    size_t modinfo_size = 0;
    for (int i = 0; i < ehdr.e_shnum; i++) {
        const char *sec_name = shstrtab + shdrs[i].sh_name;
        if (strcmp(sec_name, ".modinfo") == 0) {
            modinfo_offset = shdrs[i].sh_offset;
            modinfo_size = shdrs[i].sh_size;
            break;
        }
    }
    free(shstrtab); free(shdrs);
    if (modinfo_size == 0) { close(fd); return -1; }
    char *modinfo_buf = malloc(modinfo_size + 1);
    if (!modinfo_buf) { close(fd); return -1; }
    if (lseek64(fd, modinfo_offset, SEEK_SET) < 0 || read(fd, modinfo_buf, modinfo_size) != (ssize_t)modinfo_size) {
        free(modinfo_buf); close(fd); return -1;
    }
    modinfo_buf[modinfo_size] = '\0';
    close(fd);
    const char *vermagic = NULL;
    char *curr = modinfo_buf;
    char *limit = modinfo_buf + modinfo_size;
    while (curr < limit) {
        if (strncmp(curr, "vermagic=", 9) == 0) { vermagic = curr + 9; break; }
        curr += strlen(curr) + 1;
    }
    if (!vermagic) { free(modinfo_buf); return -1; }
    struct utsname u;
    if (uname(&u) != 0) { free(modinfo_buf); return -1; }
    size_t release_len = strlen(u.release);
    if (strncmp(vermagic, u.release, release_len) != 0 || (vermagic[release_len] != ' ' && vermagic[release_len] != '\0')) {
        free(modinfo_buf); return -1;
    }
    free(modinfo_buf);
    return 0;
}

static int adopt_zygote_env(void) {
    FILE *f = popen("pidof zygote64 zygote", "r");
    if (!f) return -1;
    int pid = 0;
    fscanf(f, "%d", &pid);
    pclose(f);
    if (!pid) return -1;
    char path[32];
    snprintf(path, sizeof(path), "/proc/%d/environ", pid);
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    static char buf[16384];
    int n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    if (n <= 0) return -1;
    buf[n] = '\0';
    for (char *p = buf, *end = buf + n; p < end; p += strlen(p) + 1) putenv(p);
    return 0;
}

static int should_ro(const char *name) {
    size_t len = strlen(name);
    if (!strcmp(name, "super") || !strcmp(name, "misc") || !strcmp(name, "steady")) return 1;
    if (len >= 2 && name[len - 2] == '_' && (name[len - 1] == 'a' || name[len - 1] == 'b')) return 1;
    return 0;
}

static int set_partitions_ro(void) {
    DIR *dir = opendir("/dev/block/by-name");
    if (!dir) return -1;
    struct dirent *ent;
    while ((ent = readdir(dir))) {
        if (!should_ro(ent->d_name)) continue;
        char path[128];
        snprintf(path, sizeof(path), "/dev/block/by-name/%s", ent->d_name);
        int fd = open(path, O_RDONLY);
        if (fd < 0) continue;
        struct stat st;
        if (fstat(fd, &st) == 0 && S_ISBLK(st.st_mode)) {
            int on = 1;
            ioctl(fd, BLKROSET, &on);
        }
        close(fd);
    }
    closedir(dir);
    return 0;
}

static int run_ctx(const char *ctx, char *const argv[]) {
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        if (ctx) {
            int fd = open("/proc/self/attr/exec", O_WRONLY);
            if (fd >= 0) { write(fd, ctx, strlen(ctx)); close(fd); }
        }
        execv(argv[0], argv);
        _exit(127);
    }
    int status;
    waitpid(pid, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

int main(void) {
    touch("/dev/dfm1");
    touch("/dev/dfm2");
    if (adopt_zygote_env()) touch("/dev/dfmw0");
    touch("/dev/dfm3");
    if (set_partitions_ro()) touch("/dev/dfmw1");
    // check vermagic
    if (check_vermagic(OPTIONAL_KSU_KO) != 0) {
        touch("/dev/dfme3");
        return 1;
    }
    touch("/dev/dfm5");
    // late-load with allow-shell
    if (run_ctx(NULL, (char *[]){ KSUD_STAGE, "late-load", "--allow-shell", "--package-name", "com.rifsxd.ksunext", NULL }) == 0) {
        touch("/dev/dfm6");
    } else {
        touch("/dev/dfme2");
        return 1;
    }
    return 0;
}
