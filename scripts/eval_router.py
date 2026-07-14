"""Avalia o classificador heurístico de complexidade contra o dataset rotulado.

Uso: python scripts/eval_router.py
Mede acurácia global, por classe e a matriz de confusão (baixa/média/alta).
"""

from __future__ import annotations

from app.routing.router import complexity_score, estimate_complexity

# (rótulo, prompt) — dataset de 98 prompts (Baixa=low, Média=medium, Alta=high).
DATASET: list[tuple[str, str]] = [
    # ---- Baixa ----
    ("low", "Crie uma expressão regular em JavaScript para validar formatos de e-mail corporativos."),
    ("low", "Formate este objeto JSON que está numa única linha para ficar indentado com 2 espaços."),
    ("low", "Converta esta função tradicional de JavaScript para uma arrow function."),
    ("low", "Adicione comentários no estilo JSDoc para esta função de cálculo de juros."),
    ("low", "Centralize esta div tanto verticalmente quanto horizontalmente usando Tailwind CSS."),
    ("low", "Crie um comando bash para listar todos os ficheiros .txt num diretório."),
    ("low", "Escreva uma tipagem TypeScript (Interface) para o retorno desta API de utilizadores."),
    ("low", "Como faço o parse de uma string para Inteiro em Python?"),
    ("low", "Extraia apenas os números desta string usando Python."),
    ("low", "Gere o código HTML básico (boilerplate) para uma página web com a tag viewport."),
    ("low", "Altere o nome das variáveis deste script para seguir o padrão camelCase."),
    ("low", "Escreva um comando Git para anular o meu último commit sem perder as alterações."),
    ("low", "Crie um dicionário em Python mapeando os códigos de estado HTTP para os seus nomes."),
    ("low", "Converta este array de strings numa string única separada por vírgulas em Java."),
    ("low", "Substitua todas as instâncias da palavra 'var' por 'let' neste ficheiro de 10 linhas."),
    ("low", "Escreva uma função em C# que verifique se uma string é um palíndromo."),
    ("low", "Como faço para arredondar um número de ponto flutuante para duas casas decimais em Go?"),
    ("low", "Crie uma máscara de input em JavaScript para números de telemóvel (XX) XXXXX-XXXX."),
    ("low", "Adicione tratamento de erros com um bloco try-catch básico nesta função de leitura."),
    ("low", "Escreva um CSS simples para um botão mudar de cor quando o rato passa por cima (hover)."),
    ("low", "Como inverto a ordem dos elementos num array em PHP?"),
    ("low", "Gere uma string aleatória de 8 caracteres alfanuméricos em Ruby."),
    ("low", "Extraia a extensão de um nome de ficheiro (ex: arquivo.pdf -> pdf) usando JavaScript."),
    ("low", "Escreva um loop 'for' clássico que itere de 1 a 100 em C++."),
    ("low", "Corrija o erro de sintaxe nesta linha de código (falta de ponto e vírgula)."),
    ("low", "Converta a cor HEX #FF5733 para o seu equivalente em RGB usando JavaScript."),
    ("low", "Escreva um comando Docker simples para descarregar a imagem do Ubuntu."),
    ("low", "Crie um ficheiro .gitignore padrão para um projeto Node.js."),
    ("low", "Oculte a barra de rolagem numa página web usando apenas CSS."),
    ("low", "Escreva uma função que retorne o valor máximo dentro de um array de inteiros em Swift."),
    ("low", "Como faço para que uma string fique totalmente em letras maiúsculas em Kotlin?"),
    ("low", "Crie um atalho de teclado no VS Code keybindings.json para formatar o documento."),
    ("low", "Converta este timestamp Unix para uma data legível em Python."),
    ("low", "Escreva uma list comprehension em Python que filtre os números pares de uma lista."),
    ("low", "Adicione a propriedade box-shadow do CSS a este cartão para dar efeito de profundidade."),
    # ---- Média ----
    ("medium", "Crie um componente de Botão em React que aceite variantes de cor (primária, secundária, perigo) via props."),
    ("medium", "Escreva uma rota POST no Express.js que receba dados de utilizador, valide com Zod e grave num array em memória."),
    ("medium", "Crie um esquema Mongoose (MongoDB) para um blog, incluindo Autores e Posts com relação entre eles."),
    ("medium", "Escreva um teste unitário usando Jest para testar a função de login de um serviço de autenticação."),
    ("medium", "Construa uma query SQL que junte a tabela de 'Clientes' com a tabela de 'Pedidos' e mostre o total gasto por cliente."),
    ("medium", "Crie um Dockerfile multi-stage para compilar e correr uma aplicação React no Nginx."),
    ("medium", "Implemente paginação numa rota de listagem de produtos usando Prisma ORM e TypeScript."),
    ("medium", "Escreva um script em Python usando requests e BeautifulSoup para fazer web scraping do título de 10 artigos numa página."),
    ("medium", "Refatore este componente React de componente de Classe para Functional Component usando Hooks (useState/useEffect)."),
    ("medium", "Configure um ficheiro docker-compose.yml que levante um serviço Node.js e um banco de dados PostgreSQL."),
    ("medium", "Crie um hook customizado em React (useFetch) que lide com estados de loading, error e data."),
    ("medium", "Escreva uma integração simples com a API do Stripe em Node.js para criar um token de pagamento."),
    ("medium", "Implemente um middleware em Express.js que verifique se o JWT no header da requisição é válido."),
    ("medium", "Crie uma animação de loading spinner usando apenas CSS keyframes e HTML."),
    ("medium", "Escreva um script de migração em SQLAlchemy (Python) para adicionar uma nova coluna 'idade' numa tabela existente."),
    ("medium", "Implemente a lógica de drag and drop (arrastar e largar) para ordenar itens numa lista usando HTML5 API."),
    ("medium", "Construa um formulário em Vue 3 (Composition API) com validação de campos obrigatórios antes do envio."),
    ("medium", "Escreva um pipeline simples de GitHub Actions que corra o npm test em cada push para a branch main."),
    ("medium", "Crie um script bash que faça backup de um diretório e envie o ficheiro tar.gz para um bucket AWS S3."),
    ("medium", "Implemente uma função de busca com debounce (espera de 300ms) em JavaScript puro."),
    ("medium", "Escreva uma query em GraphQL que busque o nome de um utilizador e as suas 5 publicações mais recentes."),
    ("medium", "Crie um serviço no Angular para partilhar o estado do utilizador logado entre diferentes componentes."),
    ("medium", "Implemente um Rate Limiter básico em memória no Node.js usando um Map para limitar requisições por IP."),
    ("medium", "Escreva um script em Python que leia um ficheiro CSV grande e insira os dados no SQLite em lotes (batch insert)."),
    ("medium", "Crie um layout responsivo de Dashboard com uma sidebar colapsável usando CSS Grid e Flexbox."),
    ("medium", "Adicione autenticação via OAuth (Google) num projeto Next.js usando o pacote NextAuth."),
    ("medium", "Escreva um teste de integração (E2E) com Cypress para verificar o fluxo de adicionar um produto ao carrinho."),
    ("medium", "Refatore este bloco de múltiplos if/else para usar o padrão de Strategy (Design Pattern) em Java."),
    ("medium", "Implemente o envio de um e-mail transacional usando a API do SendGrid em C#."),
    ("medium", "Crie uma cron job num servidor Linux que execute um script de limpeza de logs todos os domingos à meia-noite."),
    ("medium", "Implemente a lógica do jogo da velha (Tic-Tac-Toe) com verificação de vitória em JavaScript."),
    ("medium", "Escreva uma função em Go que leia dados de vários ficheiros concorrentemente usando goroutines e junte os resultados."),
    ("medium", "Configure o Nginx como um Reverse Proxy para redirecionar o tráfego da porta 80 para a porta 3000 de uma aplicação local."),
    # ---- Alta ----
    ("high", "Projete a arquitetura de microserviços (diagrama e especificação) para um sistema semelhante à Uber, incluindo comunicação assíncrona entre o serviço de localização e o de pagamento."),
    ("high", "Otimize esta query SQL que está a usar múltiplos LEFT JOIN e subqueries não indexadas, reduzindo o tempo de execução de 5s para menos de 100ms."),
    ("high", "Faça o debug desta condição de corrida (Race Condition) num sistema financeiro em Rust onde o saldo da conta está a ficar inconsistente com requisições paralelas."),
    ("high", "Escreva um compilador simples (Lexer e Parser) do zero em Python para uma linguagem matemática básica (ex: suportar A = 5 + 3 * 2)."),
    ("high", "Desenhe o esquema de base de dados e a estratégia de partição de dados (Sharding) para um serviço de mensagens (chat) que suporte 10 milhões de utilizadores ativos por dia."),
    ("high", "Identifique a vulnerabilidade de SQL Injection e Cross-Site Scripting (XSS) nesta base de código PHP legada de 300 linhas e forneça o patch seguro."),
    ("high", "Implemente o algoritmo A* (A-Star) de busca de caminhos num grid 3D usando C++, garantindo otimização máxima de memória e uso de heurística de Manhattan."),
    ("high", "Migre a lógica de estado global (Redux) de uma aplicação React gigante para uma arquitetura baseada em Zustand e React Query, mantendo os testes E2E intactos."),
    ("high", "Construa um motor de recomendação colaborativa (Collaborative Filtering) usando Python e Pandas que calcule a similaridade do cosseno entre 100 mil vetores de utilizadores em tempo real."),
    ("high", "Desenvolva o contrato inteligente (Smart Contract) em Solidity para uma plataforma de DeFi que suporte Staking com cálculo de juros compostos por bloco gerado, protegendo contra Reentrancy Attacks."),
    ("high", "Analise este core dump / log de erro de memória (OOM - Out of Memory) de um cluster Kubernetes e proponha a reestruturação dos Memory Limits e otimização do Garbage Collector do Java."),
    ("high", "Escreva um sistema de Cache Distribuído do zero em Go, implementando o algoritmo de substituição LRU (Least Recently Used) e suporte a protocolo TCP para comunicação entre os nós."),
    ("high", "Como faço a engenharia reversa desta função de ofuscação em JavaScript que usa eval e bitwise shifts para esconder a lógica de um malware? Forneça a versão de-ofuscada."),
    ("high", "Desenhe uma arquitetura Serverless completa na AWS (Lambda, API Gateway, DynamoDB, SQS) para um sistema de processamento de vídeos, incluindo o pipeline de tratamento de falhas (Dead Letter Queues)."),
    ("high", "Implemente um alocador de memória customizado (malloc e free) em C para ser usado num sistema embutido (Embedded System) com apenas 64KB de RAM, evitando fragmentação externa."),
    ("high", "Otimize este script de Machine Learning em PyTorch que treina uma rede neural convolucional para imagens médicas, distribuindo o treino em múltiplas GPUs (DistributedDataParallel)."),
    ("high", "Refatore esta arquitetura monolítica fortemente acoplada de 5 módulos para aplicar os princípios da Clean Architecture (Domain-Driven Design) em C#, separando as camadas de infraestrutura, aplicação e domínio."),
    ("high", "Escreva a configuração completa de um Service Mesh usando o Istio no Kubernetes para implementar Mutual TLS (mTLS) e roteamento de tráfego Canary (90/10) entre dois microserviços."),
    ("high", "Desenvolva o backend de um editor de texto colaborativo em tempo real (como o Google Docs) usando CRDTs (Conflict-free Replicated Data Types) e WebSockets em Elixir/Phoenix."),
    ("high", "Identifique por que esta aplicação React Native apresenta perda de frames (queda para 15 FPS) na lista infinita (FlatList) de imagens e reescreva o componente para rodar a 60 FPS consistentes."),
    ("high", "Projete a estratégia de migração Zero Downtime (sem interrupção de serviço) para mover uma base de dados MySQL de 5TB de um data center físico para o Amazon RDS."),
    ("high", "Escreva uma biblioteca criptográfica em C++ que implemente a encriptação AES-256 no modo GCM do zero (sem usar OpenSSL), garantindo proteção contra ataques de timing (Timing Attacks)."),
    ("high", "Crie um modelo de RAG (Retrieval-Augmented Generation) avançado do zero em Python usando LangChain, mas implementando uma lógica customizada de Re-ranking cruzado e Chunking semântico sensível ao contexto de documentos jurídicos."),
    ("high", "Realize uma análise de Big O (complexidade de tempo e espaço) deste algoritmo legado de cruzamento de dados. Prove matematicamente onde está o gargalo e forneça uma solução iterativa que reduza a complexidade de O(N^3) para O(N log N)."),
    ("high", "Escreva o código em assembly (x86_64) para calcular a série de Fibonacci, demonstrando a gestão manual da stack de chamadas (Call Stack) e registos de CPU."),
    ("high", "Desenvolva a engine física 2D de detecção de colisões para polígonos convexos usando o Teorema do Eixo de Separação (SAT - Separating Axis Theorem) em JavaScript/Canvas."),
    ("high", "Defina a estratégia e escreva os scripts do Terraform (Infrastructure as Code) para provisionar uma infraestrutura Multi-Cloud (AWS e Azure) que realize o failover automático via BGP e Route53 no caso da queda de um data center inteiro."),
    ("high", "Diagnostique o motivo deste script Python apresentar Memory Leak (fuga de memória) durante o processamento de 2 milhões de registos Pandas. Corrija o código usando geradores (yield) e manipulação direta de chunks em memória."),
    ("high", "Implemente o algoritmo Paxos ou Raft para garantir consenso distribuído num cluster de três nós escritos em Go, focado em eleição de líder (Leader Election)."),
    ("high", "Crie um sistema de permissões avançado baseado em atributos (ABAC - Attribute-Based Access Control) que avalie mais de 50 políticas dinâmicas (como IP, hora, cargo e nível de assinatura) em menos de 5ms usando Node.js e Redis."),
]

LEVELS = ["low", "medium", "high"]


def main() -> None:
    confusion = {a: {p: 0 for p in LEVELS} for a in LEVELS}
    per_class = {c: [0, 0] for c in LEVELS}  # [acertos, total]
    misses = []
    for label, prompt in DATASET:
        pred = estimate_complexity([{"content": prompt}])
        confusion[label][pred] += 1
        per_class[label][1] += 1
        if pred == label:
            per_class[label][0] += 1
        else:
            misses.append((label, pred, complexity_score([{"content": prompt}]), prompt))

    total = len(DATASET)
    hits = sum(per_class[c][0] for c in LEVELS)
    print(f"Acurácia global: {hits}/{total} = {hits / total:.1%}\n")
    print("Por classe:")
    for c in LEVELS:
        h, t = per_class[c]
        print(f"  {c:6}: {h}/{t} = {h / t:.0%}")
    print("\nMatriz de confusão (linha=real, coluna=previsto):")
    print(f"  {'real\\prev':>10} " + " ".join(f"{p:>7}" for p in LEVELS))
    for a in LEVELS:
        print(f"  {a:>10} " + " ".join(f"{confusion[a][p]:>7}" for p in LEVELS))
    print(f"\nErros ({len(misses)}):")
    for label, pred, sc, prompt in misses:
        print(f"  real={label:6} prev={pred:6} pts={sc:>2} | {prompt[:70]}")


if __name__ == "__main__":
    main()
