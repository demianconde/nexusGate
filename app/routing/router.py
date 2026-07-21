"""Roteador de custo (aegis-auto) — local-first com escalonamento.

Política:
- **Local é o primeiro recurso**, para tarefas simples E complexas (é gratuito).
- Só quando o local **não dá conta** (falha/erro na chamada) é que escala para um
  modelo pago hospedado — o **premium** no caso de tarefa complexa, ou o hospedado
  mais barato no caso de tarefa simples.
- Sem provedor local, escolhe direto o hospedado adequado ao tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.providers.registry import KNOWN_PROVIDERS, is_local_url
from app.routing.pricing import price_of

# Pontuação de complexidade (PT + EN — devs escrevem prompts nos dois idiomas).
# Cada categoria soma seus pontos UMA vez (se casar). Mais pontos → tarefa mais
# complexa → modelo mais capaz. Ajuste os pesos/limiares para calibrar o roteamento.
#
# Sinais de ALTA complexidade (+5): arquitetura, algoritmos avançados, sistemas
# distribuídos, otimização/performance, segurança ofensiva, baixo nível, IA/ML,
# infra avançada, matemática/provas, criptografia, engenharia de software pesada.
_HIGH_SIGNALS = re.compile(
    r"arquitetura|architecture|design de sistema|system design|microservi|"
    r"distribu[íi]|distributed|sharding|parti[çc][ãa]o de dados|"
    r"compilador|compiler|\blexer\b|\bparser\b|"
    r"race condition|condi[çc][ãa]o de corrida|"
    r"sql injection|\bxss\b|cross-site|vulnerabilidad|malware|engenharia reversa|"
    r"ofusca|timing attack|reentrancy|"
    r"\balgoritmo\b|\balgorithm|heur[íi]stic|\ba\*|"
    r"machine learning|pytorch|tensorflow|rede neural|neural network|\bgpu|"
    r"collaborative filtering|similaridade do cosseno|cosine similarity|motor de recomenda|"
    r"smart contract|solidity|\bdefi\b|blockchain|staking|"
    r"kubernetes|garbage collector|memory limit|out of memory|\boom\b|core dump|"
    r"cache distribu|distributed cache|\blru\b|"
    r"serverless|\blambda\b|dynamodb|dead letter|"
    r"alocador de mem[óo]ria|\bmalloc\b|embedded|sistema embutido|fragmenta[çc]|"
    r"clean architecture|domain-driven|\bddd\b|"
    r"service mesh|\bistio\b|\bmtls\b|\bcanary\b|"
    r"\bcrdt|conflict-free|colaborativo em tempo real|editor de texto colaborativo|"
    r"consenso|\bpaxos\b|\braft\b|leader election|elei[çc][ãa]o de l[íi]der|"
    r"memory leak|fuga de mem[óo]ria|"
    r"terraform|multi-cloud|\bfailover\b|infrastructure as code|"
    r"\baes-256\b|criptogr[áa]f|cryptograph|encripta|"
    r"\brag\b|retrieval-augmented|langchain|re-ranking|chunking|"
    r"big o|complexidade de (tempo|espa[çc]o)|prove matem|mathematical proof|o\(n|"
    r"\bassembly\b|x86|call stack|"
    r"engine f[íi]sica|separating axis|detec[çc][ãa]o de colis|"
    r"zero downtime|sem interrup[çc][ãa]o de servi[çc]o|"
    r"\babac\b|attribute-based|"
    r"otimiz|optimiz|\bfps\b|perda de frames|"
    # Novos sinais de alta complexidade:
    r"refatora|refactor|reestrutur|restructur|migra[çc][ãa]o de (banco|dados|schema)|"
    r"normaliza[çc][ãa]o|normalization|desnormaliza|denormaliz|"
    r"índice composto|composite index|plano de execu[çc][ãa]o|execution plan|"
    r"particionamento|partition|window function|fun[çc][ãa]o de janela|"
    r"transa[çc][ãa]o distribu[íi]da|two-phase commit|saga pattern|"
    r"event sourcing|\bcqrs\b|event-driven|orientado a eventos|"
    r"barramento de eventos|event bus|message broker|"
    r"circuit breaker|bulkhead|backpressure|"
    r"strangler fig|blue-green|canary deploy|feature flag|"
    r"observabilidade|observability|opentelemetry|distributed tracing|"
    r"an[áa]lise est[áa]tica|static analysis|linting|type system|sistema de tipos|"
    r"monad|functor|programa[çc][ãa]o funcional|functional programming|"
    r"metaprograma|metaprogramming|reflection|introspec[çc][ãa]o|"
    r"serializa[çc][ãa]o|serialization|desserializa|deserialization|protobuf|"
    r"gr[áa]fico de depend[êe]ncia|dependency graph|"
    r"an[áa]lise de impacto|impact analysis|"
    r"teste de carga|load test|teste de estresse|stress test|"
    r"engenharia de prompt|prompt engineering|fine.tun|fine tuning|"
    r"tokeniza[çc][ãa]o|tokenization|embedding|vetoriza[çc][ãa]o|"
    r"multimodal|vis[ãa]o computacional|computer vision|processamento de imagem|"
    r"processamento de linguagem natural|\bnlp\b|"
    r"an[áa]lise de sentimento|sentiment analysis|"
    r"extra[çc][ãa]o de entidade|named entity|"
    r"clusteriza[çc][ãa]o|clustering|classifica[çc][ãa]o|regress[ãa]o|"
    r"valida[çc][ãa]o cruzada|cross.validation|overfitting|underfitting|"
    r"gradiente descendente|gradient descent|backpropagation|"
    r"transformador|transformer|attention mechanism|mecanismo de aten[çc][ãa]o|"
    r"codifica[çc][ãa]o posicional|positional encoding|"
    r"busca sem[âa]ntica|semantic search|busca vetorial|vector search|"
    r"orquestra[çc][ãa]o|orchestration|coreografia|choreography|"
    r"idempot[êe]ncia|idempotency|entrega exactly.once|exactly.once|"
    r"consist[êe]ncia eventual|eventual consistency|"
    r"teorema \bcap\b|\bcap theorem\b|\bpacelc\b|"
    r"conten[çc][ãa]o de recursos|resource contention|"
    r"throttling|rate limiting distribu[íi]do|"
    r"assinatura digital|digital signature|certificado digital|"
    r"zero trust|confian[çc]a zero|"
    r"an[áa]lise forense|forensic|"
    r"engenharia de confiabilidade|\bsre\b|"
    r"postmortem|an[áa]lise de causa raiz|root cause|"
    r"planejamento de capacidade|capacity planning|"
    r"estima|estimat|or[çc]ament|budget",
    re.IGNORECASE,
)

# Sinais de MÉDIA complexidade (+3): frameworks/libs, integração e features reais.
_MEDIUM_SIGNALS = re.compile(
    r"\breact\b|\bexpress\b|\bvue\b|angular|next\.?js|nextauth|svelte|"
    r"mongoose|mongodb|prisma|\borm\b|sqlalchemy|sqlite|"
    r"\bjest\b|cypress|\be2e\b|teste unit[áa]rio|teste de integra|"
    r"dockerfile|docker-compose|docker compose|"
    r"graphql|middleware|\bjwt\b|oauth|"
    r"stripe|sendgrid|"
    r"\bhook\b|usefetch|usestate|useeffect|composition api|"
    r"web scraping|beautifulsoup|"
    r"github actions|\bpipeline\b|ci/cd|"
    r"rate limiter|debounce|drag and drop|"
    r"\bcron\b|reverse proxy|nginx|"
    r"design pattern|padr[ãa]o de|strategy|"
    r"goroutines|concorrent|concurrency|concorr[êe]ncia|"
    r"\bjoin\b|\bsql\b|query sql|junte a tabela|batch insert|"
    r"backup|tar\.gz|\bs3\b|"
    r"formul[áa]rio|componente|component|dashboard|sidebar|layout responsivo|"
    r"jogo da velha|tic-tac-toe|spinner|anima[çc][ãa]o|keyframes|"
    r"pagina[çc][ãa]o|migra[çc][ãa]o|migration|"
    # Novos sinais de média complexidade:
    r"\bapi rest\b|\brestful\b|endpoint|crud|"
    r"autentica[çc][ãa]o|authentication|autoriza[çc][ãa]o|authorization|"
    r"login|logout|registro|register|sign.up|sign.in|"
    r"upload|download|file upload|upload de arquivo|"
    r"valida[çc][ãa]o de (formul[áa]rio|dados|input)|form validation|"
    r"tratamento de erro|error handling|try.catch|"
    r"log|logging|debug|depura[çc][ãa]o|"
    r"configura[çc][ãa]o|configuration|\.env|environment|"
    r"vari[áa]vel de ambiente|environment variable|"
    r"requisi[çc][ãa]o http|http request|\bajax\b|\bfetch\b|axios|"
    r"promise|async.await|callback|"
    r"internacionaliza[çc][ãa]o|\bi18n\b|localiza[çc][ãa]o|\bl10n\b|"
    r"acessibilidade|\ba11y\b|wcag|"
    r"seo|search engine|otimiza[çc][ãa]o de busca|"
    r"cookie|session|localstorage|"
    r"websocket|\bsocket\.io\b|tempo real|real.time|"
    r"notifica[çc][ãa]o|notification|push|"
    r"fila|queue|mensageria|messaging|"
    r"agendamento|scheduling|tarefa agendada|scheduled task|"
    r"relat[óo]rio|report|exportar|csv|excel|pdf|"
    r"importa[çc][ãa]o|import|exporta[çc][ãa]o|export|"
    r"integra[çc][ãa]o|integration|webhook|"
    r"chatbot|assistente virtual|virtual assistant|"
    r"tradu[çc][ãa]o|translation|idioma|language|"
    r"formata[çc][ãa]o|formatting|markdown|html|css|"
    r"responsivo|responsive|mobile.first|"
    r"dark mode|tema claro|tema escuro|light theme|dark theme|"
    r"pagamento|payment|checkout|carrinho|cart|"
    r"busca|search|filtro|filter|ordena[çc][ãa]o|sort|"
    r"coment[áa]rio|comment|avalia[çc][ãa]o|rating|review|"
    r"perfil de usu[áa]rio|user profile|configura[çc][ãa]o de conta|"
    r"recupera[çc][ãa]o de senha|password reset|esqueci minha senha|"
    r"convite|invite|compartilhar|share|"
    r"dashboard anal[íi]tico|analytics|m[ée]trica|metric|"
    r"gr[áa]fico|chart|visualiza[çc][ãa]o de dados|data visualization|"
    r"tutorial|guia|guide|documenta[çc][ãa]o|documentation|"
    r"boas pr[áa]ticas|best practice|"
    r"refatora[çc][ãa]o simples|pequena melhoria|cleanup|"
    r"renomear|rename|mover arquivo|move file|"
    r"adicionar|add|remover|remove|atualizar|update|"
    r"corrigir|fix|bug|erro|error|problema|issue",
    re.IGNORECASE,
)

# Sinais de BAIXA complexidade (+1): tarefas triviais que qualquer modelo resolve.
# Estes sinais REDUZEM a pontuação se a tarefa for claramente simples.
_LOW_SIGNALS = re.compile(
    r"(\bol[áa]\b|hello|oi|hey|sauda[çc][ãa]o|greeting)\s*$|"
    r"^(sim|n[ãa]o|yes|no|ok|okay|certo|claro)\s*$|"
    r"obrigado|thanks|thank you|valeu|"
    r"o que [ée] (voc[êe]|vc)|what are you|who are you|quem [ée] voc[êe]|"
    r"como vai|how are you|tudo bem|"
    r"me diga uma piada|tell me a joke|conte uma piada|"
    r"qual [ée] a capital|what is the capital|"
    r"quantos (dias|meses|anos)|how many (days|months|years)|"
    r"qual [ée] a data|what (day|date) is|que dia [ée]|"
    r"traduza|translate|traduzir|"
    r"resuma|summarize|resumir|sum[áa]rio|"
    r"explique|explain|explicar|o que [ée]|what is|defina|define|"
    r"liste|list|listar|enumere|enumerate|"
    r"converta|convert|converter|"
    r"formate|format|formatar|"
    r"corrija|correct|corrigir|revise|revisar|"
    r"escreva|write|escrever|redija|"
    r"gere|generate|gerar|crie|create|criar|"
    r"qual a diferen[çc]a|what('s| is) the difference|compare|comparar|"
    r"d[êe] exemplos|give examples|exemplos de|"
    r"como (fazer|criar|usar|configurar|instalar)|how (to|do I|can I)|"
    r"qual [ée] o melhor|what is the best|which is better|"
    r"me ajude|help me|ajuda|socorro|"
    r"preciso de ajuda|I need help|"
    r"pode me (dizer|explicar|ajudar)|can you (tell|explain|help)|"
    r"voc[êe] (pode|consegue)|can you|"
    r"d[êe].me|me d[êe]|me (mostre|ensine|fale)|show me|tell me|"
    r"qual [ée] o significado|what does .* mean|"
    r"o que significa|what is the meaning|"
    r"qual [ée] a (defini[çc][ãa]o|fun[çc][ãa]o)|what is the (definition|function)|"
    r"como funciona|how does .* work|"
    r"para que serve|what is .* (for|used for)|"
    r"quando (usar|utilizar)|when (to use|should I use)|"
    r"onde (encontrar|achar|buscar)|where (to find|can I find)|"
    r"por que|why|por qu[êe]|"
    r"qual [ée] a (melhor|pior|maior|menor)|what is the (best|worst|biggest|smallest)|"
    r"top \d+|top (dez|cinco|tr[êe]s)|"
    r"dicas|tips|tricks|truques|"
    r"passo a passo|step by step|tutorial|"
    r"para iniciante|for beginner|b[áa]sico|basic|"
    r"simples|simple|f[áa]cil|easy|r[áa]pido|quick|"
    r"exemplo|example|sample|"
    r"c[óo]digo|code|script|programa|"
    r"fun[çc][ãa]o|function|m[ée]todo|method|classe|class|"
    r"vari[áa]vel|variable|constante|constant|"
    r"loop|la[çc]o|for|while|if|else|switch|"
    r"array|lista|list|dicion[áa]rio|dictionary|objeto|object|"
    r"string|n[úu]mero|number|inteiro|integer|booleano|boolean|"
    r"json|xml|csv|yaml|"
    r"html|css|javascript|python|java|typescript|"
    r"git|github|commit|push|pull|branch|merge|"
    r"npm|pip|yarn|pnpm|"
    r"linux|windows|mac|ubuntu|"
    r"vscode|visual studio|intellij|eclipse|"
    r"terminal|console|bash|shell|cmd|"
    r"servidor|server|cliente|client|"
    r"banco de dados|database|tabela|table|"
    r"select|insert|update|delete|where|"
    r"get|post|put|delete|patch|"
    r"status code|status http|200|404|500|"
    r"header|body|query param|path param|"
    r"token|senha|password|hash|"
    r"url|uri|link|endere[çc]o|"
    r"ip|dns|dominio|domain|host|porta|port|"
    r"firewall|proxy|vpn|ssl|tls|https|"
    r"cache|cookie|session|storage|"
    r"erro|error|exce[çc][ãa]o|exception|falha|failure|"
    r"debug|log|print|console|"
    r"teste|test|assert|expect|"
    r"build|compile|run|execute|start|stop|restart|"
    r"install|uninstall|update|upgrade|downgrade|"
    r"deploy|release|publish|"
    r"monitor|alert|alarm|warning|"
    r"backup|restore|snapshot|"
    r"scale|escalar|load balance|balanceador|"
    r"documenta[çc][ãa]o|readme|changelog|"
    r"coment[áa]rio|comment|anota[çc][ãa]o|note|"
    r"cor|color|fonte|font|tamanho|size|margem|margin|padding|"
    r"bot[ãa]o|button|link|texto|text|imagem|image|[íi]cone|icon|"
    r"menu|navega[çc][ãa]o|navigation|header|footer|"
    r"modal|popup|tooltip|dropdown|"
    r"tabela|table|lista|list|grid|flex|"
    r"input|textarea|select|checkbox|radio|"
    r"loading|carregando|spinner|skeleton|"
    r"vazio|empty|sem dados|no data|"
    r"confirma[çc][ãa]o|confirmation|di[áa]logo|dialog|"
    r"toast|snackbar|alerta|alert|banner|"
    r"breadcrumb|pagination|tabs|accordion|"
    r"carrossel|carousel|slider|slideshow|"
    r"calend[áa]rio|calendar|date picker|time picker|"
    r"upload de (arquivo|imagem)|file upload|image upload|"
    r"arrastar e soltar|drag and drop|"
    r"copiar e colar|copy paste|"
    r"desfazer|undo|refazer|redo|"
    r"salvar|save|cancelar|cancel|fechar|close|"
    r"enviar|submit|limpar|clear|resetar|reset|"
    r"buscar|search|filtrar|filter|ordenar|sort|"
    r"editar|edit|visualizar|view|detalhes|details|"
    r"criar novo|create new|adicionar novo|add new|"
    r"confirmar|confirm|rejeitar|reject|aprovar|approve|"
    r"ativar|activate|desativar|deactivate|habilitar|enable|desabilitar|disable|"
    r"bloquear|block|desbloquear|unblock|"
    r"arquivar|archive|excluir|delete|restaurar|restore|"
    r"importar|import|exportar|export|baixar|download|"
    r"copiar|copy|colar|paste|recortar|cut|"
    r"imprimir|print|compartilhar|share|"
    r"curtir|like|favorito|favorite|seguir|follow|"
    r"comentar|comment|responder|reply|mencionar|mention|"
    r"notificar|notify|assinar|subscribe|inscrever|"
    r"convite|invite|aceitar|accept|recusar|decline|"
    r"perfil|profile|conta|account|configura[çc][ãa]o|settings|"
    r"ajuda|help|suporte|support|contato|contact|"
    r"sobre|about|termos|terms|privacidade|privacy|"
    r"faq|perguntas frequentes|frequently asked|"
    r"feedback|sugest[ãa]o|suggestion|reportar|report|"
    r"erro|error|bug|problema|problem|issue|"
    r"obrigado|thanks|valeu|agradecido|"
    r"bom dia|boa tarde|boa noite|good morning|good afternoon|good evening|"
    r"tchau|adeus|bye|see you|at[eé] logo|"
    r"parab[ée]ns|congratulations|feliz|happy|"
    r"desculpe|sorry|perd[ãa]o|my bad|"
    r"por favor|please|se puder|if you can|"
    r"com licen[çc]a|excuse me|"
    r"entendi|understood|compreendi|got it|"
    r"ok|okay|certo|right|correto|correct|"
    r"sim|yes|n[ãa]o|no|talvez|maybe|"
    r"concordo|agree|discordo|disagree|"
    r"bom|good|[óo]timo|great|excelente|excellent|"
    r"ruim|bad|p[ée]ssimo|terrible|horr[íi]vel|"
    r"legal|cool|interessante|interesting|"
    r"chato|boring|entediante|"
    r"[úu]til|useful|in[úu]til|useless|"
    r"importante|important|urgente|urgent|"
    r"f[áa]cil|easy|dif[íi]cil|difficult|hard|"
    r"r[áa]pido|fast|quick|devagar|slow|lento|"
    r"grande|big|large|pequeno|small|little|"
    r"muito|very|many|pouco|few|little|"
    r"sempre|always|nunca|never|[àa]s vezes|sometimes|"
    r"hoje|today|amanh[ãa]|tomorrow|ontem|yesterday|"
    r"agora|now|depois|later|antes|before|"
    r"aqui|here|l[áa]|there|ali|"
    r"dentro|inside|fora|outside|"
    r"perto|near|longe|far|"
    r"cima|up|baixo|down|esquerda|left|direita|right|"
    r"primeiro|first|[úu]ltimo|last|pr[óo]ximo|next|anterior|previous|"
    r"tudo|all|everything|nada|nothing|algum|some|nenhum|none|"
    r"mais|more|menos|less|melhor|better|pior|worse|"
    r"igual|equal|same|diferente|different|"
    r"verdade|true|falso|false|"
    r"ligado|on|desligado|off|"
    r"aberto|open|fechado|closed|"
    r"in[íi]cio|start|begin|fim|end|finish|"
    r"entrada|input|sa[íi]da|output|"
    r"sucesso|success|falha|failure|erro|error|"
    r"completo|complete|incompleto|incomplete|"
    r"v[áa]lido|valid|inv[áa]lido|invalid|"
    r"obrigat[óo]rio|required|opcional|optional|"
    r"padr[ãa]o|default|personalizado|custom|"
    r"p[úu]blico|public|privado|private|protegido|protected|"
    r"est[áa]tico|static|din[âa]mico|dynamic|"
    r"local|remoto|remote|online|offline|"
    r"s[íi]ncrono|sync|ass[íi]ncrono|async|"
    r"bloqueante|blocking|n[ãa]o.bloqueante|non.blocking|"
    r"thread|processo|process|mem[óo]ria|memory|cpu|disco|disk|"
    r"rede|network|internet|intranet|"
    r"navegador|browser|mobile|desktop|tablet|"
    r"android|ios|windows|linux|macos|"
    r"chrome|firefox|safari|edge|opera|"
    r"frontend|backend|fullstack|full.stack|"
    r"devops|sre|sysadmin|administrador|"
    r"estagi[áa]rio|junior|pleno|senior|tech lead|"
    r"scrum|kanban|agile|[áa]gil|waterfall|cascata|"
    r"sprint|daily|retrospective|planning|"
    r"task|tarefa|story|hist[óo]ria|[ée]pico|epic|"
    r"bug|hotfix|feature|melhoria|improvement|"
    r"pull request|merge request|code review|revis[ãa]o|"
    r"branch|feature branch|main|master|develop|"
    r"release|tag|version|vers[ãa]o|"
    r"hotfix|patch|minor|major|"
    r"semver|versionamento sem[âa]ntico|semantic versioning|"
    r"changelog|release notes|notas de vers[ãa]o|"
    r"roadmap|planejamento|planning|cronograma|"
    r"okr|kpi|meta|goal|objetivo|objective|"
    r"m[ée]trica|metric|indicador|indicator|"
    r"dashboard|relat[óo]rio|report|gr[áa]fico|chart|"
    r"an[áa]lise|analysis|diagn[óo]stico|diagnostic|"
    r"monitoramento|monitoring|observabilidade|observability|"
    r"alerta|alert|notifica[çc][ãa]o|notification|"
    r"incidente|incident|problema|problem|outage|"
    r"manuten[çc][ãa]o|maintenance|janela|window|"
    r"migra[çc][ãa]o|migration|atualiza[çc][ãa]o|upgrade|"
    r"rollback|revert|desfazer|undo|"
    r"backup|restore|recupera[çc][ãa]o|recovery|"
    r"disaster recovery|continuidade|continuity|"
    r"conformidade|compliance|lgpd|gdpr|sox|hipaa|"
    r"auditoria|audit|log|registro|"
    r"rastreabilidade|traceability|"
    r"governan[çc]a|governance|"
    r"seguran[çc]a|security|prote[çc][ãa]o|protection|"
    r"privacidade|privacy|dados pessoais|personal data|"
    r"consentimento|consent|opt.in|opt.out|"
    r"termos de uso|terms of service|"
    r"pol[íi]tica de privacidade|privacy policy|"
    r"cookie|tracking|rastreamento|"
    r"lgpd|gdpr|ccpa|"
    r"anpd|autoridade|authority|"
    r"penalidade|penalty|multa|fine|san[çc][ãa]o|"
    r"vazamento|leak|breach|incidente|"
    r"notifica[çc][ãa]o|notification|comunica[çc][ãa]o|"
    r"direito do titular|data subject|"
    r"acesso|access|retifica[çc][ãa]o|rectification|"
    r"exclus[ãa]o|erasure|portabilidade|portability|"
    r"oposi[çc][ãa]o|objection|revis[ãa]o|review|"
    r"decis[ãa]o automatizada|automated decision|"
    r"leg[íi]timo interesse|legitimate interest|"
    r"execu[çc][ãa]o de contrato|contract|"
    r"obriga[çc][ãa]o legal|legal obligation|"
    r"consentimento expl[íi]cito|explicit consent|"
    r"dados sens[íi]veis|sensitive data|"
    r"crian[çc]a|child|adolescente|adolescent|"
    r"encarregado|dpo|data protection officer|"
    r"relat[óo]rio de impacto|dpia|"
    r"transfer[êe]ncia internacional|international transfer|"
    r"cl[áa]usula padr[ãa]o|standard contractual|"
    r"binding corporate rules|"
    r"certifica[çc][ãa]o|certification|selo|seal|"
    r"c[óo]digo de conduta|code of conduct|",
    re.IGNORECASE,
)

_SIGNALS: list[tuple[re.Pattern[str], int]] = [
    (_HIGH_SIGNALS, 5),
    (_MEDIUM_SIGNALS, 3),
    (_LOW_SIGNALS, 1),
]

# Limiares de pontuação → nível de complexidade (baixa/média/alta).
# Ajustados para refletir os novos pesos (+5/+3/+1).
_MEDIUM_THRESHOLD = 3
_HIGH_THRESHOLD = 6

# Três tiers por provedor: barato (baixa), médio (média) e premium (alta).
PROVIDER_TIERS: dict[str, dict[str, str]] = {
    "openai": {"cheap": "gpt-4o-mini", "mid": "gpt-4o", "premium": "gpt-4o"},
    "anthropic": {
        "cheap": "claude-3-5-haiku",
        "mid": "claude-3-5-sonnet",
        "premium": "claude-3-5-sonnet",
    },
    "google": {
        "cheap": "gemini-3.1-flash-lite",
        "mid": "gemini-2.5-flash",
        "premium": "gemini-2.5-pro",
    },
    "qwen": {"cheap": "qwen-turbo", "mid": "qwen-plus", "premium": "qwen-max"},
    "deepseek": {"cheap": "deepseek-chat", "mid": "deepseek-chat", "premium": "deepseek-reasoner"},
    "mistral": {"cheap": "mistral-small", "mid": "mistral-medium", "premium": "mistral-large"},
    "groq": {"cheap": "llama-3.1-8b", "mid": "llama-3.3-70b", "premium": "llama-3.3-70b"},
    "together": {"cheap": "llama-3.1-8b", "mid": "llama-3.1-70b", "premium": "llama-3.1-70b"},
    # OpenRouter agrega vários provedores; trio "Equilibrado" (custo→qualidade).
    # Ajuste os modelos conforme os disponíveis na sua conta OpenRouter.
    "openrouter": {
        "cheap": "openai/gpt-5-nano",
        "mid": "openai/gpt-5-mini",
        "premium": "anthropic/claude-opus-4.7",
    },
}


class _KeyLike(Protocol):
    provider: str
    base_url: str | None
    default_model: str | None


@dataclass
class Route:
    provider_key: _KeyLike
    model: str
    baseline_model: str
    complexity: str
    tier: str
    is_local: bool
    escalation: Route | None = None


def complexity_score(messages: list[dict]) -> int:
    """Soma os pontos de complexidade dos sinais de texto + tamanho + código."""
    text = " ".join(str(m.get("content", "")) for m in messages)
    score = 0
    for pattern, points in _SIGNALS:
        if pattern.search(text):
            score += points
    n = len(text)
    if n > 6000:  # ~1500 tokens
        score += 3
    elif n > 2000:
        score += 2
    elif n > 800:
        score += 1
    if "```" in text:  # lida com bloco de código
        score += 1
    return score


def estimate_complexity(messages: list[dict]) -> str:
    """Retorna o nível de complexidade: 'low', 'medium' ou 'high' (por pontuação)."""
    score = complexity_score(messages)
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _is_local(pk: _KeyLike) -> bool:
    spec = KNOWN_PROVIDERS.get(pk.provider)
    return bool(spec and spec.local) or is_local_url(pk.base_url)


def _tier_model(pk: _KeyLike, tier: str) -> str | None:
    if _is_local(pk):
        return pk.default_model
    tiers = PROVIDER_TIERS.get(pk.provider)
    if tiers:
        # mid ausente cai para premium; premium ausente cai para cheap.
        return tiers.get(tier) or tiers.get("premium") or tiers.get("cheap") or pk.default_model
    return pk.default_model


def _best_hosted(keys: list[_KeyLike], tier: str) -> tuple[_KeyLike, str] | None:
    """Provedor hospedado mais barato para o tier."""
    cands: list[tuple[float, _KeyLike, str]] = []
    for pk in keys:
        if _is_local(pk):
            continue
        model = _tier_model(pk, tier)
        if model:
            inp, out = price_of(model)
            cands.append((inp + out, pk, model))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    return cands[0][1], cands[0][2]


def choose_route(complexity: str, provider_keys: list[_KeyLike]) -> Route | None:
    tier = {"high": "premium", "medium": "mid", "low": "cheap"}.get(complexity, "cheap")

    local_keys = [pk for pk in provider_keys if _is_local(pk) and pk.default_model]
    hosted_tier = _best_hosted(provider_keys, tier)
    hosted_premium = _best_hosted(provider_keys, "premium")
    baseline_model = (hosted_premium or hosted_tier or (None, None))[1]

    if local_keys:
        lpk = local_keys[0]
        escalation = None
        if hosted_tier:
            e_pk, e_model = hosted_tier
            escalation = Route(
                provider_key=e_pk,
                model=e_model,
                baseline_model=e_model,
                complexity=complexity,
                tier=tier,
                is_local=False,
            )
        return Route(
            provider_key=lpk,
            model=lpk.default_model,
            baseline_model=baseline_model or lpk.default_model,
            complexity=complexity,
            tier=tier,
            is_local=True,
            escalation=escalation,
        )

    if hosted_tier:
        h_pk, h_model = hosted_tier
        return Route(
            provider_key=h_pk,
            model=h_model,
            baseline_model=baseline_model or h_model,
            complexity=complexity,
            tier=tier,
            is_local=False,
        )

    return None
