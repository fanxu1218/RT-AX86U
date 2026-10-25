#include <unistd.h>
int check_if_file_exist(const char *path){return access(path,F_OK)==0;}
