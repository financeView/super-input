/* Read one raw pinyin key per line and emit the librime candidate menu. */
#include <rime_api.h>
#include <stdio.h>
#include <string.h>

#define LINE_CAP 4096

int main(int argc, char **argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: dump_candidates <shared_data_dir> <user_data_dir>\n");
    return 2;
  }

  RimeApi *rime = rime_get_api();
  if (!rime) {
    fprintf(stderr, "failed to get librime API table\n");
    return 1;
  }

  RIME_STRUCT(RimeTraits, traits);
  traits.app_name = "super-input-baseline";
  traits.shared_data_dir = argv[1];
  traits.user_data_dir = argv[2];
  traits.modules = NULL;
  rime->setup(&traits);
  rime->initialize(&traits);
  rime->start_maintenance(True);
  rime->join_maintenance_thread();

  RimeSessionId session = rime->create_session();
  if (!session) {
    fprintf(stderr, "failed to create librime session\n");
    rime->finalize();
    return 1;
  }
  if (!rime->select_schema(session, "superpinyin")) {
    fprintf(stderr, "failed to select superpinyin schema\n");
    rime->destroy_session(session);
    rime->finalize();
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
      rime->destroy_session(session);
      rime->finalize();
      return 2;
    }

    rime->clear_composition(session);
    for (size_t i = 0; i < length; ++i) {
      unsigned char key = (unsigned char)line[i];
      if (key >= 'a' && key <= 'z') {
        rime->process_key(session, (int)key, 0);
      }
    }

    RIME_STRUCT(RimeContext, context);
    if (!rime->get_context(session, &context)) {
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
    rime->free_context(&context);
    fflush(stdout);
  }

  rime->destroy_session(session);
  rime->finalize();
  return 0;
}
