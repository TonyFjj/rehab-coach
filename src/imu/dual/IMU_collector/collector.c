#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <stdint.h>
#include <math.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <limits.h>
#include <libgen.h>

#define BAUDRATE B115200
#define IMU_PORT_LEFT  "/dev/ttyACM0"
#define IMU_PORT_RIGHT "/dev/ttyACM1"
#define CSV_PATH_MAX   256
#define FLUSH_THRESHOLD 50
#define MAX_RAW_FRAMES 120000
#define ACC_RANGE   16.0
#define GYRO_RANGE  2000.0
#define ANGLE_RANGE 180.0

typedef struct {
    int16_t ax, ay, az, wx, wy, wz, roll, pitch, yaw;
} IMURaw;

typedef struct {
    const char *port;
    const char *hand;
    char csv_path[CSV_PATH_MAX];
    volatile int running;
    int total_frames;
    int target_frames;
    int last_flush;
    IMURaw *raw;
    int raw_count;
    int raw_capacity;
} Ctx;

static char g_csv_dir[PATH_MAX];

static const char *collector_data_dir(void)
{
    if (g_csv_dir[0] != '\0') {
        return g_csv_dir;
    }

    const char *env = getenv("IMU_DATA_DIR");
    if (env != NULL && env[0] != '\0') {
        snprintf(g_csv_dir, sizeof(g_csv_dir), "%s", env);
    } else {
        char exe[PATH_MAX];
        ssize_t n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
        if (n > 0) {
            char exe_copy[PATH_MAX];
            exe[n] = '\0';
            strncpy(exe_copy, exe, sizeof(exe_copy) - 1);
            exe_copy[sizeof(exe_copy) - 1] = '\0';
            char candidate[PATH_MAX];
            snprintf(candidate, sizeof(candidate), "%s/../data", dirname(exe_copy));
            char resolved[PATH_MAX];
            if (realpath(candidate, resolved) != NULL) {
                strncpy(g_csv_dir, resolved, sizeof(g_csv_dir) - 1);
            } else {
                strncpy(g_csv_dir, candidate, sizeof(g_csv_dir) - 1);
            }
        } else {
            strncpy(g_csv_dir, "./data", sizeof(g_csv_dir) - 1);
        }
    }
    g_csv_dir[sizeof(g_csv_dir) - 1] = '\0';
    return g_csv_dir;
}

static void make_csv_path(const char *hand, char *out)
{
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    mkdir(collector_data_dir(), 0755);
    snprintf(out, CSV_PATH_MAX, "%s/IMU_%s_%04d%02d%02d_%02d%02d%02d.csv",
             collector_data_dir(), hand,
             t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
             t->tm_hour, t->tm_min, t->tm_sec);
}

static int store(Ctx *ctx, IMURaw *f)
{
    if (ctx->raw_count >= ctx->raw_capacity) {
        int n = ctx->raw_capacity == 0 ? 4096 : ctx->raw_capacity * 2;
        if (n > MAX_RAW_FRAMES) n = MAX_RAW_FRAMES;
        IMURaw *p = realloc(ctx->raw, n * sizeof(IMURaw));
        if (!p) {
            fprintf(stderr, "[%s] OOM\n", ctx->hand);
            return -1;
        }
        ctx->raw = p;
        ctx->raw_capacity = n;
    }
    ctx->raw[ctx->raw_count++] = *f;
    return 0;
}

static void find_stable(Ctx *ctx, int *s, int *c)
{
    *s = 0;
    *c = 100;
    int found = 0;

    for (int i = 400; i < 600 && i + 100 <= ctx->raw_count; i += 10) {
        double sum = 0, sum2 = 0;
        for (int j = i; j < i + 100; j++) {
            double a = sqrt((double)ctx->raw[j].ax * ctx->raw[j].ax +
                            (double)ctx->raw[j].ay * ctx->raw[j].ay +
                            (double)ctx->raw[j].az * ctx->raw[j].az);
            sum += a;
            sum2 += a * a;
        }
        double m = sum / 100;
        double v = sum2 / 100 - m * m;
        double sdev = (v > 0) ? sqrt(v) : 0;
        if (m > 500 && sdev < m * 0.2) {
            *s = i;
            *c = 100;
            found = 1;
            break;
        }
    }

    if (!found) {
        *s = (ctx->raw_count > 500) ? 500 : 0;
        *c = 100;
        if (*s + *c > ctx->raw_count)
            *c = ctx->raw_count - *s;
    }
}

static void save_csv(Ctx *ctx)
{
    if (ctx->raw_count == 0) {
        fprintf(stderr, "[%s] no data\n", ctx->hand);
        return;
    }
    int rs, rc;
    find_stable(ctx, &rs, &rc);

    double bw = 0, bx = 0, bz = 0;
    for (int i = rs; i < rs + rc && i < ctx->raw_count; i++) {
        bw += ctx->raw[i].wx;
        bx += ctx->raw[i].wy;
        bz += ctx->raw[i].wz;
    }
    bw /= rc;
    bx /= rc;
    bz /= rc;

    double as = ACC_RANGE * 9.8 / 32768.0;
    double gs = GYRO_RANGE / 32768.0;
    double an = 180.0 / 32768.0;

    FILE *f = fopen(ctx->csv_path, "w");
    if (!f) {
        perror("fopen");
        return;
    }
    fprintf(f, "# IMU [%s] - physical\n", ctx->hand);
    fprintf(f, "# Acc +/-%.0fg Gyro +/-%.0fdps\n", ACC_RANGE, GYRO_RANGE);
    fprintf(f, "# Gyro bias(raw) wx=%.0f wy=%.0f wz=%.0f\n", bw, bx, bz);
    fprintf(f, "# 100Hz\n");
    fprintf(f, "ax_mps2,ay_mps2,az_mps2,wx_dps,wy_dps,wz_dps,roll_deg,pitch_deg,yaw_deg\n");

    for (int i = 0; i < ctx->raw_count; i++) {
        fprintf(f, "%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
                ctx->raw[i].ax * as,
                ctx->raw[i].ay * as,
                ctx->raw[i].az * as,
                (ctx->raw[i].wx - bw) * gs,
                (ctx->raw[i].wy - bx) * gs,
                (ctx->raw[i].wz - bz) * gs,
                ctx->raw[i].roll * an,
                ctx->raw[i].pitch * an,
                ctx->raw[i].yaw * an);
    }
    fclose(f);
    printf("[%s] saved %d frames -> %s\n", ctx->hand, ctx->raw_count, ctx->csv_path);
}

static void *thread_func(void *arg)
{
    Ctx *ctx = (Ctx *)arg;
    int fd = open(ctx->port, O_RDONLY | O_NOCTTY);
    if (fd < 0) {
        fprintf(stderr, "[%s] open %s failed\n", ctx->hand, ctx->port);
        ctx->running = 0;
        pthread_exit(NULL);
    }

    struct termios t;
    tcgetattr(fd, &t);
    cfsetospeed(&t, BAUDRATE);
    cfsetispeed(&t, BAUDRATE);
    t.c_cflag &= ~PARENB;
    t.c_cflag &= ~CSTOPB;
    t.c_cflag &= ~CSIZE;
    t.c_cflag |= CS8;
    t.c_cflag |= CREAD | CLOCAL;
    t.c_lflag &= ~(ICANON | ECHO | ECHOE | ECHONL | ISIG);
    t.c_iflag &= ~(IXON | IXOFF | IXANY | IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL);
    t.c_oflag &= ~OPOST;
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 0;
    tcsetattr(fd, TCSANOW, &t);

    time_t t0 = time(NULL);
    time_t dur = ctx->target_frames / 100;
    unsigned char buf[4096];
    int cnt = 0;

    while (ctx->running && (time(NULL) - t0 < dur)) {
        fd_set r;
        FD_ZERO(&r);
        FD_SET(fd, &r);
        struct timeval tv = {0, 1000};
        select(fd + 1, &r, NULL, NULL, &tv);
        if (!FD_ISSET(fd, &r)) continue;

        int n = read(fd, buf, sizeof(buf));
        if (n <= 0) continue;

        for (int i = 0; i < n - 1; i++) {
            if (buf[i] == 0x55 && buf[i + 1] == 0x61 && i + 20 <= n) {
                IMURaw imu;
                imu.ax = (int16_t)(buf[i + 2] | (buf[i + 3] << 8));
                imu.ay = (int16_t)(buf[i + 4] | (buf[i + 5] << 8));
                imu.az = (int16_t)(buf[i + 6] | (buf[i + 7] << 8));
                imu.wx = (int16_t)(buf[i + 8] | (buf[i + 9] << 8));
                imu.wy = (int16_t)(buf[i + 10] | (buf[i + 11] << 8));
                imu.wz = (int16_t)(buf[i + 12] | (buf[i + 13] << 8));
                imu.roll = (int16_t)(buf[i + 14] | (buf[i + 15] << 8));
                imu.pitch = (int16_t)(buf[i + 16] | (buf[i + 17] << 8));
                imu.yaw = (int16_t)(buf[i + 18] | (buf[i + 19] << 8));
                if (store(ctx, &imu) != 0) {
                    ctx->running = 0;
                    break;
                }
                cnt++;
                i += 19;
            }
        }

        if (cnt - ctx->last_flush >= FLUSH_THRESHOLD) {
            ctx->last_flush = cnt;
            ctx->total_frames = cnt;
            printf("[%s] %d frames\n", ctx->hand, cnt);
        }
    }

    ctx->total_frames = cnt;
    ctx->running = 0;
    close(fd);
    printf("[%s] done: %d frames\n", ctx->hand, cnt);
    pthread_exit(NULL);
}

int main(int argc, char *argv[])
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <seconds>\n", argv[0]);
        return 1;
    }
    int dur = atoi(argv[1]);
    if (dur <= 0) {
        fprintf(stderr, "Invalid time\n");
        return 1;
    }

    mkdir(collector_data_dir(), 0755);
    printf("[路径] 数据目录: %s\n", collector_data_dir());

    printf("============================================================\n");
    printf("  Dual IMU Collector  |  %d seconds @ 100Hz\n", dur);
    printf("  Left : %s\n", IMU_PORT_LEFT);
    printf("  Right: %s\n", IMU_PORT_RIGHT);
    printf("============================================================\n");

    Ctx L = {0}, R = {0};
    L.port = IMU_PORT_LEFT;
    L.hand = "L";
    L.running = 1;
    L.target_frames = dur * 100;
    R.port = IMU_PORT_RIGHT;
    R.hand = "R";
    R.running = 1;
    R.target_frames = dur * 100;
    make_csv_path("L", L.csv_path);
    make_csv_path("R", R.csv_path);
    printf("Left  -> %s\n", L.csv_path);
    printf("Right -> %s\n", R.csv_path);

    pthread_t tl, tr;
    pthread_create(&tl, NULL, thread_func, &L);
    pthread_create(&tr, NULL, thread_func, &R);

    while ((L.running && L.total_frames < L.target_frames) ||
           (R.running && R.total_frames < R.target_frames)) {
        sleep(1);
        printf("  L:%d/%d  R:%d/%d\n",
               L.total_frames, L.target_frames,
               R.total_frames, R.target_frames);
    }
    L.running = 0;
    R.running = 0;
    pthread_join(tl, NULL);
    pthread_join(tr, NULL);

    printf("\nConverting...\n");
    save_csv(&L);
    save_csv(&R);
    free(L.raw);
    free(R.raw);
    printf("Done.\n");
    return 0;
}
