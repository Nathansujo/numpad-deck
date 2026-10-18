# Numpad Deck

Transforma o teclado numérico em um "deck" de atalhos (estilo Stream Deck) **sem perder o teclado numérico normal**. A luz do Num Lock mostra em qual modo você está.

| Luz do Num Lock | Modo | O que acontece |
|---|---|---|
| Acesa | **Padrão** | O teclado numérico digita números normalmente. |
| Apagada | **Deck** | As teclas `0`–`9` executam a ação programada na página atual. |

Teclas de controle (só funcionam no **modo deck**):

| Tecla | Função |
|---|---|
| `Num Lock` | Alterna padrão ⇄ deck (e acende/apaga a luz — quem faz isso é o próprio Windows). Também **cancela** um fluxo que esteja rodando (por exemplo, numa pausa longa) |
| `/` | Volta uma página |
| `*` | Avança uma página (as páginas são infinitas) |
| `-` | Mostra um **pop-up grande** com a imagem e o nome resumido de cada tecla da página atual (apertando `-` de novo, ou clicando no pop-up, ele fecha; fecha sozinho depois de alguns segundos) |

No **modo padrão**, `/`, `*` e `-` continuam funcionando normalmente, mas o computador **apita** (dois tons descendo) avisando que o deck não foi acionado. Dá para desligar em *Opções*. Ao trocar de página com `/` ou `*`, a mesma prévia aparece rapidinho (opção de teste, também desligável). No painel, o botão **Ver prévia** mostra o mesmo pop-up.

## Páginas com nome

Clique em **Página N** no topo do painel para abrir a lista de páginas: dê um nome a cada uma (ex.: `ECAC`, `Programas Python`), vá para ela ou remova as que estão vazias. **+ Nova** (no topo ou na lista) cria o **próximo número que ainda não existe** (1 → 2 → 3…) e já vai para ele; depois é só clicar no nome para renomear. O nome aparece no título do painel, no pop-up grande do `-` (“Página 10 · ECAC”) e ao escolher a página nos blocos *Chamar outra tecla* e *Ir para página*. As páginas continuam infinitas: digite qualquer número em **Ir** (ou num bloco) e ela passa a existir quando você programar uma tecla nela. Uma página só sai da lista se estiver sem teclas (a página 1 e a atual não saem).

## Programando uma tecla: fluxo de blocos

Clique numa tecla no painel, dê um nome, escolha uma **imagem** e monte o **fluxo**: cada tecla executa seus blocos **de cima para baixo**, na ordem que está no painel.

- **+ Adicionar bloco** cria um bloco novo no fim; o **+** entre dois blocos insere ali.
- **Clique no bloco** para abrir e **escolher/trocar a função** dele.
- Mude a ordem com **↑ ↓** ou arrastando pela alça **⠿**; **✕** remove; **▶** testa só aquele bloco; **Testar fluxo** roda tudo.

### Blocos

| Bloco | O que faz |
|---|---|
| **Atalho de teclado** | Grava um comando (Ctrl + V, Win + D…) e o executa |
| **Digitar texto** | Digita um texto pronto, tecla por tecla |
| **Colar texto** | Põe o texto na área de transferência e aperta Ctrl + V: instantâneo e sem erro de acento/emoji |
| **Clique** | Marca um ponto (a tela escurece) e clica: esquerdo, direito, do meio, simples ou duplo. O ponto pode valer para a **tela inteira** ou para a **janela de um programa** (veja abaixo) |
| **Mover mouse** · **Rolar a tela** | Leva o cursor a um ponto sem clicar · gira a roda do mouse |
| **Esperar** | Espera **um tempo** (0,05 a 600 s) **ou uma condição** (veja abaixo) |
| **Repetir** | Repete N vezes os blocos que vêm logo abaixo |
| **Se / senão** | Confere uma condição e executa os blocos de baixo (então) ou os seguintes (senão) |
| **Contador / variável** | Soma, define ou zera um número que você usa como `{nome}` em qualquer texto |
| **Chamar outra tecla** | Executa o fluxo de qualquer tecla de qualquer página (o painel não deixa salvar chamadas em ciclo) |
| **Ir para página** | Muda o deck para outra página no meio do fluxo |
| **Abrir programa ou pasta** | `.exe`, `.bat`, atalhos, documentos, scripts `.py`, pastas, ou um nome como `chrome` (com argumentos opcionais) |
| **Abrir site** | Abre um endereço no navegador padrão, ou no **navegador do Deck** (veja abaixo) |
| **Comando** | Roda um comando de PowerShell ou CMD, sem janela; pode esperar terminar e avisar se der erro |
| **WhatsApp (abrir conversa)** | Abre a conversa com o número e a mensagem já escritos (quem envia é você, ou um fluxo com “Clicar na página web”) |
| **Clicar na página web** · **Preencher campo da página** | Agem num elemento da página (por seletor CSS); esperam ele aparecer sozinhos |
| **Volume e mídia** | Volume +/−, mudo, play/pausa, próxima/anterior |
| **Print da tela** | Salva um PNG em Imagens\NumpadDeck |
| **Bloquear PC / monitor** | Bloqueia o Windows ou desliga o monitor |
| **Aviso** | Avisa que terminou: **pop-up** na tela, **mensagem no WhatsApp** (link `wa.me` + Enter, ou Evolution API) ou **Bloco de Notas** (veja abaixo) |

### Avisos

O bloco **Aviso** tem três jeitos de avisar:

- **Pop-up na tela** — título (opcional) e mensagem, **tamanho** pequeno, médio ou grande e **onde aparece**: centro, topo, embaixo, os quatro cantos ou **personalizado**. As miniaturas no painel mostram a tela e onde o aviso fica. Em *Personalizado*, o botão **Desenhar na tela** escurece a tela e você **arrasta um retângulo** exatamente onde (e do tamanho que) quer o aviso; as linhas tracejadas mostram os três tamanhos de referência. Fica na tela pelo tempo escolhido (0 = até você clicar nele); clicar fecha. Dois avisos no mesmo lugar: o novo cobre o antigo. Use o **▶** do bloco para ver na hora.
- **Mensagem no WhatsApp** — número (com DDI e DDD, ex.: `5577991831413`) e mensagem. Dois jeitos de enviar:
  - **Link do WhatsApp + Enter** (padrão): o Deck abre `https://wa.me/<número>?text=<mensagem>` (a mensagem é codificada sozinha, com acentos e quebras de linha), no WhatsApp Web ou no app, conforme o seu computador; espera o tempo que você definir (padrão 10 s) e **aperta Enter** para enviar. Não precisa de servidor nem de chave. Enquanto espera, não troque de janela nem digite: o Enter vai para a janela que estiver em primeiro plano. Aumente a espera se o WhatsApp Web demorar a carregar.
  - **Evolution API**: sai do WhatsApp conectado na sua Evolution, sem abrir nada na tela e sem usar o teclado. Configure uma vez em **Opções → WhatsApp (Evolution API)**: endereço, nome da **instância** e **chave (apikey)**; há um botão de teste. A chave fica só neste computador, em `segredos.json` (fora do Git) e nunca volta ao painel.
- **Bloco de Notas** — dois modos: **abrir um TXT que já existe** (nome do arquivo + pasta, ou caminho completo — ex.: o TXT que o seu programa Python gerou) ou **rodar um script Python / PowerShell / CMD e mostrar a saída**: o Deck espera o programa terminar, guarda tudo que ele escreveu na tela (e os erros) num TXT e abre no Bloco de Notas. O TXT é criado ao lado do script (ou na pasta que você indicar; sem nada, em `saidas\` dentro da pasta de dados) e tem o nome que você escolher (ou um com data e hora).

Em todos os avisos vale `{contador}`, `{data}` e `{hora}`.

### Clique (e Mover mouse) na tela inteira ou na janela de um programa

Em **Clique** e **Mover mouse** você escolhe a que a posição se refere:

- **A tela inteira**: ponto fixo na tela (x, y), como sempre foi.
- **A janela de um programa**: você marca o ponto clicando dentro do programa; o Deck guarda o **título da janela** e **onde o ponto fica dentro dela**. A cada execução ele acha a janela, vê onde ela está e de que tamanho, e clica no ponto correspondente — então, se o programa mudou de Full HD para uma janelinha de 1000×400, o clique acompanha. Duas formas de acompanhar:
  - **Proporcional** (padrão): o ponto fica na mesma fração da janela (ex.: 75% da largura, 25% da altura). Serve quando o conteúdo estica junto com a janela.
  - **Fixo a partir de um canto**: mantém a distância em pixels de um dos quatro cantos. Serve para botões de barra de ferramentas ou de rodapé que não esticam.
  - A área considerada é a de dentro da janela (sem barra de título e bordas). Marque o ponto clicando dentro dela.
  - No título, deixe só a parte que não muda (ex.: `Excel`, e não `Planilha 3 - Excel`). Se houver mais de uma janela com esse texto, vale a que está em primeiro plano, senão a de cima.
  - Por padrão o Deck **traz a janela para a frente** (e restaura se estiver minimizada) antes de clicar; dá para desligar. Se a janela ainda não abriu, ponha antes um bloco **Esperar** → janela.

### Esperar por uma condição (sem chutar o tempo)

No bloco **Esperar**, escolha “até uma condição”. O fluxo só segue quando a condição for verdadeira (ou falsa, se escolher “até sumir”), conferida a cada ¼ de segundo. Você define o tempo máximo e o que fazer se ele acabar (parar e avisar, ou seguir mesmo assim). Num Lock cancela a espera.

- **Uma janela do Windows**: o título contém um texto (ex.: `Excel`), em primeiro plano ou apenas aberta.
- **A cor de um ponto da tela**: marque o ponto e a cor (botão que muda de cinza para verde, fim de um carregamento…), com tolerância.
- **Algo na página web**: um elemento do HTML (seletor CSS, ex.: `#enviar`, `button.ok`) ou um texto na página. Como achar o seletor: clique com o botão direito no elemento → *Inspecionar* → botão direito no HTML destacado → *Copy* → *Copy selector*.

Os mesmos três tipos de condição servem para o bloco **Se / senão**.

### Navegador do Deck (para olhar o HTML da página)

Para conferir elementos da página, o programa precisa controlar o navegador. Ele abre um **Chrome (ou Edge) só dele**, com perfil próprio e a porta de depuração ligada **apenas em 127.0.0.1**. Para usar: no bloco **Abrir site**, marque “Abrir no navegador do Deck”. Entre nas suas contas nele uma vez (Google, WhatsApp Web…) e o login fica guardado nesse perfil (`%APPDATA%\NumpadDeck\perfil-navegador`). O Chrome não permite controle remoto no seu perfil de uso diário, por isso é um perfil separado. Se tiver várias abas, você pode filtrar a aba pelo endereço/título.

### Grupos: repetir e se/senão

“Repetir” e “Se” valem para os **N blocos logo abaixo deles**; no painel esses blocos aparecem recuados, com a marca “então”, “senão” ou “repete”. Ao inserir um bloco no meio de um grupo com o **+**, ele entra no grupo; ao remover, o grupo encolhe. Grupos podem ficar dentro de grupos. Se a quantidade passar do fim do fluxo, o painel avisa em vermelho e não deixa salvar.

### Contador e variáveis

O bloco **Contador / variável** guarda um número (fica salvo mesmo fechando o programa). Em qualquer texto de qualquer bloco (digitar, colar, aviso, site, comando, WhatsApp, preencher campo, condições…) escreva `{pedido}` e ele vira o valor atual. `{data}` (dd/mm/aaaa) e `{hora}` (hh:mm) também existem. Exemplo: `Somar 1 a {pedido}` + `Digitar texto: Pedido {pedido}`.

## Instalar e rodar (Python 3.10+ no Windows)

```
pip install -r requirements.txt   # flask, pynput, Pillow (imagens do pop-up) e websocket-client (navegador do Deck)
python main.py
```

O painel abre no navegador (`http://127.0.0.1:5077`). O programa continua rodando em segundo plano mesmo se você fechar a aba. Para encerrar: *Opções → Encerrar o programa*.

## Gerar o executável

**No Linux, sem GitHub:** `sudo apt install wine64 curl` e `./build-no-linux.sh`. Ele instala o Python de Windows dentro do Wine (só na primeira vez) e gera `dist/NumpadDeck.exe`.

**No Linux, pelo GitHub:** o `.exe` é um programa de Windows e só pode ser montado por um Windows. Outro jeito é deixar o GitHub fazer (grátis, repositório privado): instale `git` e `gh`, rode `gh auth login` uma vez e depois `./gerar-exe-pelo-github.sh`. O script envia o projeto para um repositório seu, manda montar e baixa o resultado em `dist/NumpadDeck.exe` (uns 3 a 6 minutos). Ou, sem script: envie o projeto ao GitHub e rode *Actions → Gerar executavel → Run workflow*.

**No Windows:** dê dois cliques em `build.bat`. O arquivo `dist\NumpadDeck.exe` é o que você coloca na Área de Trabalho:

- Abrir o `.exe` mostra o painel (se já estiver rodando, só abre o painel).
- Em *Opções*, marque **Iniciar junto com o Windows** para ele subir sozinho em segundo plano.

## Atualização automática

O `NumpadDeck.exe` (baixado da Release do GitHub) procura uma versão mais nova ao abrir. Se houver, baixa, confere (origem oficial, tamanho, SHA-256), troca o arquivo e reinicia sozinho; as suas teclas e configurações não mudam. Pode desligar em Opções ou usar "Procurar atualização agora".

Para publicar uma atualização: `git add -A && git commit -m "..." && git push && git tag v1.2 && git push --tags` (use sempre um número maior que o anterior). O GitHub gera o .exe com esse número gravado dentro.

Observações: o repositório precisa ser público; a primeira versão com atualizador precisa ser instalada manualmente; o .exe não é assinado, então o Windows pode avisar na primeira execução; rodando por `python main.py` nada se atualiza.

## Usar em mais de um computador

Você **não precisa** gerar `.exe` toda hora. Três jeitos, do mais simples:

1. **GitHub + atualizar.bat (recomendado).** Coloque esta pasta num repositório (privado, se quiser). Em cada computador: `git clone <endereço>` uma vez, depois `instalar.bat` (cria um ambiente isolado e instala as bibliotecas) e `iniciar.bat` para abrir. Para atualizar: feche o programa (*Opções → Encerrar*) e dê dois cliques em `atualizar.bat` (faz `git pull` e atualiza as bibliotecas). Como o programa roda direto do código, não precisa build; o “iniciar com o Windows” passa a apontar para essa pasta.
2. **`.exe` pronto vindo do GitHub.** O arquivo `.github/workflows/build.yml` gera o `NumpadDeck.exe` nos servidores do GitHub. Publique uma versão (`git tag v1.1 && git push --tags`) e baixe o `.exe` na página *Releases*; ou rode manualmente em *Actions → Gerar executavel → Run workflow*. Bom para um computador sem Python nem Git.
3. **Pasta sincronizada.** Para os computadores compartilharem **a mesma configuração** (teclas, imagens, contadores), defina a variável de ambiente `NUMPAD_DECK_DIR` apontando para uma pasta do OneDrive/Google Drive/Dropbox (`setx NUMPAD_DECK_DIR "D:\OneDrive\NumpadDeck"`, depois feche e abra o programa). Atenção: **posições de clique, cores de pixel e caminhos de programas mudam de um computador para outro** (resolução, escala, usuário). Por isso, em geral é melhor ter uma configuração por computador e copiar só o que servir.

O código fica no Git; a configuração (`config.json`, imagens, perfil do navegador) fica em `%APPDATA%\NumpadDeck\` e não vai para o repositório.

## Onde ficam os dados

`%APPDATA%\NumpadDeck\` — `config.json` (páginas, nomes das páginas, teclas e contadores), `segredos.json` (chave da Evolution API), `saidas\` (TXT das saídas de programas), `imagens\`, `perfil-navegador\` (navegador do Deck) e `numpad_deck.log` (erros). Para mudar a porta, edite `"porta"` no `config.json` com o programa fechado.

## Limites e cuidados

- **Programas rodando como administrador** não repassam o teclado para um programa comum: nesses programas, no modo deck, as teclas do numpad vão "vazar". Se precisar, abra o NumpadDeck como administrador.
- Antivírus podem estranhar o `.exe` (qualquer programa que lê o teclado inteiro e é empacotado com PyInstaller costuma ser marcado). Se acontecer, use `python main.py` ou crie uma exceção.
- Enquanto você grava um comando, o teclado fica "preso" ao gravador por até 20 s (para o comando não ser executado de verdade); o botão *Cancelar* solta.
- O painel só aceita chamadas da própria página aberta pelo programa (token + verificação de Host), porque qualquer site aberto no navegador consegue chamar `127.0.0.1`.
- Os `.py` são executados com o Python instalado no PATH quando você usa o `.exe`; rodando com `python main.py`, usa o mesmo Python.
- Se um bloco falhar (arquivo não encontrado, tempo esgotado numa espera, elemento que não apareceu…), o computador apita e mostra o motivo; o resto do fluxo é interrompido.
- O bloco **Comando** executa exatamente o que estiver escrito: coloque só o que você entende. A porta do navegador do Deck fica restrita ao próprio computador (127.0.0.1).
- Fluxos antigos (versão 1, uma ação por tecla) são convertidos automaticamente em fluxos de um bloco.

## Testes

```
python -m unittest discover -s tests
```

Cobrem as regras de teclas (modo padrão/deck, `/`, `*`, `-`, repetição, Num Lock, gravação de atalho), a execução dos fluxos (ordem, pausa, chamadas entre teclas, ciclos, cancelamento pelo Num Lock), a configuração e a API do painel. A parte que depende do Windows (hook de teclado, pop-ups, tela de clique, som, início automático, janelas/cor de pixel, volume, bloquear, print, `.exe`) só pode ser conferida no seu computador.

## Arquivos

`main.py` (entrada) · `posicao.py` (clique relativo à janela) · `navegador.py` (navegador do Deck) · `avisos.py` (pop-up, WhatsApp/Evolution, saída para o Bloco de Notas) · `instalar.bat`, `iniciar.bat`, `atualizar.bat`, `build.bat`, `build-no-linux.sh`, `gerar-exe-pelo-github.sh` · `nucleo.py` (regras das teclas) · `configuracao.py` (JSON, validação, imagens) · `servidor.py` + `web/index.html` (painel) · `hook_win.py`, `ui_tk.py` (pop-ups), `plataforma_win.py` (partes do Windows) · `teclas.py` (nomes das teclas)

