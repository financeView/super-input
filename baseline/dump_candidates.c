/* Read one raw pinyin key per line and emit the librime candidate menu. */
#include <rime_api.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LINE_CAP 4096

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: dump_candidates <data_dir>\n");
    return 2;
  }

  RIME_STRUCT(RimeTraits, traits);
  traits.app_name = "super-input-baseline";
  traits.user_data_dir = argv[1];
  traits.shared_data_dir = argv[1];
  traits.modules = NULL;
  RimeSetup(&traits);
  RimeInitialize(&traits);
  RimeStartMaintenance(1);
  RimeJoinMaintenance();

  RimeSessionId session = RimeCreateSession();
  if (!session) {
    fprintf(stderr, "failed to create librime session\n");
    RimeFinalize();
    return 1;
  }

  char line[LINE_CAP];
  int reported_page_size = 0;
  while (fgets(line, sizeof(line), stdin)) {
    size_t length = strlen(line);
    while (length && (line[length - 1] == '\n' || line[length - 1] == '\r')) {
      line[--length] = '\0';
    }
    if (!length) continue;
    if (length == sizeof(line) - 1 && line[length - 1] != '\n') {
      fprintf(stderr, "input line exceeds %d bytes\n", LINE_CAP - 1);
      RimeDestroySession(session);
      RimeFinalize();
      return 2;
    }

    RimeClearComposition(session);
    for (size_t i = 0; i < length; ++i) {
      unsigned char key = (unsigned char)line[i];
      if ((key >= 'a' && key <= 'z') || key == 'v') {
        RimeProcessKey(session, (int)key, 0);
      }
    }

    RIME_STRUCT(RimeContext, context);
    if (!RimeGetContext(session, &context)) {
      printf("%s\t-\t\n", line);
      fflush(stdout);
      continue;
    }
    if (!reported_page_size) {
      fprintf(stderr, "page_size=%d\n", context.menu.page_size);
      reported_page_size = 1;
    }
    for (int i = 0; i < context.menu.num_candidates; ++i) {
      const char *candidate = context.menu.candidates[i].text;
      printf("%s\t%d\t%s\n", line, i, candidate ? candidate : "");
    }
    RimeFreeContext(&context);
    fflush(stdout);
  }

  RimeDestroySession(session);
  RimeFinalize();
  return 0;
}
