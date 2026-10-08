# Uandex TV — Sistema de Gestão (versão inicial)

Painel web responsivo para gerenciar clientes e pagamentos. Pode ser usado localmente ou publicado no PythonAnywhere.

## Publicar gratuitamente no PythonAnywhere

> Importante: o plano gratuito tem limites e o site pode expirar após um mês de acordo com as regras atuais da plataforma; será necessário acompanhar a conta e renovar quando a plataforma solicitar. Faça backup do banco `uandex_tv.db` regularmente. Não use este plano como única cópia dos dados do negócio.

1. Crie uma conta em https://www.pythonanywhere.com/ (plano gratuito).
2. Entre no painel e abra **Files**.
3. Crie uma pasta chamada `uandex_tv` dentro da sua pasta inicial.
4. Envie os arquivos deste ZIP para `/home/SEU_USUARIO/uandex_tv/`. Envie `app.py`, `requirements.txt`, as pastas `templates` e `static`. Não envie o arquivo `passenger_wsgi.py.example` como se fosse o WSGI final.
5. Abra **Consoles** e inicie um console **Bash**. Execute, substituindo `SEU_USUARIO` pelo seu nome de usuário do PythonAnywhere:

   ```bash
   cd /home/SEU_USUARIO/uandex_tv
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

6. Abra a aba **Web** e escolha **Add a new web app**. Selecione o domínio gratuito `SEU_USUARIO.pythonanywhere.com`, depois **Manual configuration** e a versão Python oferecida pelo painel.
7. Na seção **Code**, configure o **Source code** para `/home/SEU_USUARIO/uandex_tv` e o **Working directory** para o mesmo caminho.
8. Na seção **Virtualenv**, informe `/home/SEU_USUARIO/uandex_tv/.venv`.
9. Na seção **WSGI configuration file**, clique no link do arquivo e substitua o conteúdo pelo modelo abaixo. Troque `SEU_USUARIO` em todos os lugares e crie uma chave secreta longa e aleatória no lugar de `COLOQUE_UMA_CHAVE_LONGA_E_ALEATORIA_AQUI`:

   ```python
   import os
   import sys

   project_home = '/home/SEU_USUARIO/uandex_tv'
   if project_home not in sys.path:
       sys.path.insert(0, project_home)

   os.environ['SECRET_KEY'] = 'COLOQUE_UMA_CHAVE_LONGA_E_ALEATORIA_AQUI'

   from app import app as application
   ```

10. Volte à aba **Web** e pressione **Reload**. Abra `https://SEU_USUARIO.pythonanywhere.com`.
11. Entre com o usuário `admin` e a senha inicial `MudeEstaSenha123!`. **Imediatamente, abra “Alterar senha” e troque por uma senha forte e exclusiva.**
12. Cadastre um cliente fictício para testar. Depois, remova o cadastro de teste.

## Se der erro
- Abra a aba **Web** e confira **Error log**.
- Confirme que o caminho da pasta e o nome de usuário estão corretos.
- Confirme que o ambiente virtual está apontando para `/home/SEU_USUARIO/uandex_tv/.venv`.
- Depois de alterar arquivos, pressione **Reload** na aba Web.

## Usar no celular
Depois de publicar, abra o endereço `https://SEU_USUARIO.pythonanywhere.com` no Safari/Chrome. Você pode usar **Compartilhar → Adicionar à Tela de Início** no iPhone para criar um atalho.

## Backup
No painel Files, copie periodicamente `uandex_tv.db` para um local seguro. Não compartilhe esse arquivo: ele contém os cadastros e o histórico do sistema.

## Primeiro acesso
- Usuário: `admin`
- Senha inicial: `MudeEstaSenha123!`

## O que já tem
- Login administrativo com senha armazenada em hash
- Painel com contagem de clientes, previsão mensal e pagamentos do mês
- Cadastro, edição, busca e exclusão de clientes
- Campos para contato, aplicativo, dispositivo, login/usuário, valor e vencimento
- Sinalização automática de clientes vencidos e próximos do vencimento
- Histórico de pagamentos e formas de pagamento
- Atalho para abrir conversa do WhatsApp
- Layout responsivo para celular e computador

## Limitações
Esta é uma versão inicial. O sistema não realiza cobranças, pagamentos, ativações ou renovações automáticas em serviços externos. Evite cadastrar senhas de acesso dos clientes em texto aberto. O plano gratuito pode ter limitações e não substitui backup.
