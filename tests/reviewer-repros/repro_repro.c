/* Mirrors OpenBanglaState::keyEvent/commit/selectCandidate call sequence. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "riti.h"

static RitiContext *ctx; static Suggestion *sug;
static uint16_t k(char c){
  switch(c){
  case 'a':return VC_A;case 'b':return VC_B;case 'e':return VC_E;case 'i':return VC_I;case 'k':return VC_K;
  case 'm':return VC_M;case 'n':return VC_N;case 'o':return VC_O;case 'r':return VC_R;case 'v':return VC_V;
  case 't':return VC_T;case 'h':return VC_H;case 'y':return VC_Y;case ':':return VC_COLON;case ')':return VC_PAREN_RIGHT;
  } fprintf(stderr,"bad key %c\n",c); exit(2);
}
static void dump(void){
  if(riti_suggestion_is_lonely(sug)){char*t=riti_suggestion_get_pre_edit_text(sug,0);printf("   lonely '%s'\n",t);riti_string_free(t);return;}
  size_t n=riti_suggestion_get_length(sug), p=riti_suggestion_previously_selected_index(sug);
  printf("   [presel=%zu] ",p);
  for(size_t i=0;i<n;i++){char*t=riti_suggestion_get_suggestion(sug,i);printf("%zu:'%s' ",i,t);riti_string_free(t);} printf("\n");
}
/* type word, then commit candidate `pick` (-1 = whatever is preselected, like Space) */
static const char*want=NULL;
static void word(const char*w,int pick){
  for(const char*c=w;*c;c++){ if(sug) riti_suggestion_free(sug); sug=riti_get_suggestion_for_key(ctx,k(*c),0,0); }
  printf("typed '%s'\n",w); dump();
  if(want && !riti_suggestion_is_lonely(sug)){size_t n=riti_suggestion_get_length(sug);for(size_t i=0;i<n;i++){char*t=riti_suggestion_get_suggestion(sug,i);if(!strcmp(t,want))pick=(int)i;riti_string_free(t);}want=NULL;}
  size_t idx = riti_suggestion_is_lonely(sug)?0:(pick<0?riti_suggestion_previously_selected_index(sug):(size_t)pick);
  char*t=riti_suggestion_get_pre_edit_text(sug,idx); printf("   COMMIT idx %zu '%s'\n",idx,t); riti_string_free(t);
  riti_context_candidate_committed(ctx,idx); riti_suggestion_free(sug); sug=NULL;
}
int main(int argc,char**argv){
  Config*cfg=riti_config_new();
  riti_config_set_layout_file(cfg, argc>2?argv[2]:"avro_phonetic");
  riti_config_set_phonetic_suggestion(cfg,1); riti_config_set_suggestion_include_english(cfg,1);
  riti_config_set_fixed_suggestion(cfg,1);
  riti_config_set_smart_quote(cfg,1);
  ctx=riti_context_new_with_config(cfg);
  if(argc<2) return 0;
  if(!strcmp(argv[1],"dup")){
    word("ami",1);         /* user picks 2nd candidate for "ami" once */
    word("amie",-1);       /* plain Space commits */
    word("amier",-1);
    word("kotha",1);       /* any non-default commit flushes the map to disk */
  } else if(!strcmp(argv[1],"dup2")){
    want="অমি"; word("ami",-1);
    word("amie",-1); word("amier",-1); word("amier",-1);
  } else if(!strcmp(argv[1],"crash")){
    want=":)"; word(":)",-1);   /* user arrows to the literal ":)" candidate */
    word(":e",-1);              /* any later word ":"+suffix */
  } else if(!strcmp(argv[1],"crash2")){
    word(":e",-1);
  }
  printf("done\n"); return 0;
}
