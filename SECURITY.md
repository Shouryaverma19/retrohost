# Segurança, limitações e uso responsável

O HomeGames é um projeto **doméstico**, pensado para rodar **dentro da sua rede local (LAN)** — um servidor de jogos retrô que você acessa pelo navegador de outros dispositivos da sua casa. Esta seção é honesta sobre o que isso implica em segurança, quais são os riscos conhecidos, e o que você **não** deve fazer.

## ⚠️ Não exponha à internet / não suba em cloud pública

**Não há autenticação em nenhuma rota.** Qualquer pessoa que alcance a porta `8000` (e as portas de mídia) pode listar/iniciar/parar jogos, configurar storage e enviar input. Isso é aceitável numa LAN doméstica de confiança, mas significa:

- **Nunca exponha as portas do HomeGames diretamente à internet** (port forwarding no roteador, IP público, etc.).
- **Nunca suba este container em um provedor de cloud público** (AWS, GCP, Azure, VPS, etc.) com as portas acessíveis. Sem autenticação e com privilégios elevados (ver abaixo), seria um alvo trivial.
- Se você *precisa* acessar de fora de casa, use uma **VPN** para entrar na sua LAN — não exponha o serviço.

Se um dia o projeto for usado fora de uma LAN de confiança, é **obrigatório** adicionar antes: autenticação, HTTPS/TLS, e revisão dos privilégios do container.

## Riscos e vulnerabilidades conhecidas

### Input remoto sem autenticação
O navegador captura teclado/gamepad e envia ao servidor por WebSocket (`/ws/input`), que injeta o input no emulador. **Não há validação de origem nem autenticação** nesse canal. Numa LAN, o risco é baixo (quem está na sua rede já tem acesso). Exposto à internet, qualquer um poderia injetar comandos no jogo em execução. É mais um motivo para **não expor à internet**.

### Container roda com `--privileged`
O container exige `--privileged` para montar o storage de rede (`mount -t cifs`). Isso dá ao container acesso amplo ao host. É aceitável para uso doméstico/pessoal, mas:

- **Não rode imagens/container de terceiros não confiáveis com `--privileged`.**
- Em uma máquina compartilhada ou sensível, considere rodar **sem storage de rede** (ROMs por volume local `-v`), o que dispensa o `--privileged` — uma redução de privilégio para `--cap-add SYS_ADMIN` só quando há CIFS é uma melhoria planejada, ainda não implementada.

### Credenciais do storage de rede (CIFS/Samba)
A senha do compartilhamento Samba é gravada em arquivo `chmod 600` (`/data/homegames-credentials` no container, `/etc/samba/...` no Pi), **nunca em texto plano em config exposta** nem na resposta da API. Ainda assim, é uma credencial em disco: use um **usuário Samba dedicado e de baixo privilégio** (só leitura das ROMs), não credenciais administrativas.

### Sem isolamento entre sessões / single-user
Há **um jogo por vez**, estado em memória, sem múltiplas sessões ou isolamento entre usuários. Não é um serviço multi-tenant — é para uma casa.

### Storage de rede e a injeção de comando de mount
O backend monta CIFS executando `mount` com parâmetros vindos da interface web. A entrada é restrita (destino de mount fixo), mas como qualquer recurso que constrói comando de sistema a partir de input, é mais uma razão para **manter o serviço em rede de confiança**.

## BIOS e ROMs — responsabilidade do usuário

**Este projeto não distribui, não inclui e não fornece BIOS ou ROMs de jogos.**

- A **BIOS** de consoles (ex: PS1) é propriedade do fabricante. Você deve **extraí-la do seu próprio console** ou obtê-la de forma legal. O HomeGames apenas lê a BIOS que *você* colocar no storage.
- As **ROMs** dos jogos são propriedade dos respectivos detentores de direitos. Você deve **possuir uma cópia legal** do jogo (geralmente, fazer o *dump* da sua própria mídia física). Baixar ROMs de jogos que você não possui é ilegal na maioria das jurisdições.

O HomeGames é uma ferramenta de **streaming/emulação da sua própria biblioteca legal** — não um meio de distribuir conteúdo protegido. O uso para pirataria não é apoiado e é de inteira responsabilidade de quem o faz.

## Resumo: uso recomendado

✅ **Faça:** rode na sua LAN doméstica, com suas próprias ROMs/BIOS legais, acessando de dispositivos da sua casa.

❌ **Não faça:** expor à internet, subir em cloud pública, usar com ROMs/BIOS obtidas ilegalmente, ou rodar imagens não confiáveis com `--privileged`.
