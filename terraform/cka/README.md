# Lab CKA Ubuntu sur Proxmox

Ce stack transpose le [Vagrantfile fourni](reference/Vagrantfile) en deux VM
Proxmox. Il prépare Ubuntu, SSH et le partage de fichiers ; Kubernetes,
containerd, kubeadm et le CNI restent à installer pendant les exercices.

Le cycle de vie de ce lab appartient exclusivement à `terraform/cka`, avec son
propre état. Il ne fait pas partie du `clusters` map de `terraform/proxmox`,
n’est pas géré par CAPI et n’héberge aucun workload de production. `labmgmt`
et `labprod` gardent leurs propriétaires habituels.

## Topologie déclarée

| VM | ID Proxmox | vCPU | RAM Mio | IP du lab | IP administration |
| --- | --- | --- | --- | --- | --- |
| k8s-master | 620 | 2 | 1800 | 192.168.60.20/24 | 192.168.10.20/24 |
| k8s-worker-1 | 621 | 2 | 3000 | 192.168.60.21/24 | 192.168.10.21/24 |

Chaque VM possède un disque de 32 Gio sur `local-lvm`, dans le pool `CKA`.
L’image Canonical Ubuntu Server 22.04 est épinglée à `release-20261020`, avec
son SHA-256 officiel. L’image Bento/VirtualBox est remplacée par l’image cloud
Ubuntu de même version, adaptée à KVM/Proxmox.

Sur le bridge VLAN-aware `vmbr0`, la première carte utilise le VLAN 10 et sa
passerelle existante `192.168.10.1` pour SSH et les téléchargements. La seconde
utilise le VLAN 60, sans passerelle par défaut, pour les échanges du lab. Les
deux noms dans `/etc/hosts` pointent sur les adresses `192.168.60.x`.
Pour les exercices Kubernetes, choisir explicitement l’interface/IP du lab
lors de la configuration de kubelet, kubeadm et du CNI. Le VLAN du lab ne
constitue pas à lui seul une frontière de sécurité : les VM disposent aussi
de leur interface d’administration.

## Prérequis et propriétaires

- Le propriétaire Proxmox fournit le nœud `homelab`, le bridge `vmbr0`
  VLAN-aware, les stockages `local` et `local-lvm`, et la capacité disque/RAM.
  Le [runbook Proxmox](../proxmox/README.md) documente ces prérequis.
- Le stack réseau LabOps reste propriétaire du routage et de la sortie Internet
  du VLAN 10. Les deux IP d’administration, deux IP du lab, MAC et ID de VM
  déclarés doivent être libres avant la première création.
- Le jeton API existant est une entrée sensible, récupérée depuis le
  gestionnaire de secrets de l’opérateur ou son fichier ignoré
  `terraform/proxmox/credentials.auto.tfvars`. Il nécessite les droits de
  création/configuration des VM, de pool, de stockage dédié, et de téléchargement
  d’image sur `local`. Voir le [runbook du jeton](../proxmox/README.md#create-the-terraform-api-token).
  Le fichier n’est ni copié dans ce stack ni affiché dans les journaux.
- Le transfert de snippets et l’import de disque utilisent l’accès SSH de
  l’opérateur Proxmox, `bingo` avec sudo sans mot de passe. Les chemins et
  l’identité sont paramétrables. Sa récupération est documentée dans
  [l’enrôlement du workspace](../../hacks/README.md).
- La clé publique demandée par l’utilisateur est suivie dans `keys/bingops.pub`.
  La clé privée correspondante reste une entrée externe de l’opérateur ; elle
  ne doit pas être copiée dans Git, les VM ou l’état Terraform. Sur le workspace
  courant, elle est disponible dans `~/.ssh/homeops-proxmox`.
  Le commentaire `root@localhost` de la clé ne change pas le compte des VM :
  la connexion se fait en `ubuntu`, avec sudo.

## Créer ou reprendre la création

Depuis la racine de ce dépôt, adapter au besoin les valeurs par défaut dans un
fichier `.tfvars` ignoré. Ne pas modifier les autres stacks pour créer ce lab.
Le téléchargement de provider et le plan nécessitent un accès réseau/API.

```sh
cd /home/coder/projects/labops
terraform -chdir=terraform/cka init -input=false
terraform -chdir=terraform/cka fmt -check
terraform -chdir=terraform/cka validate

# Le plan et ses journaux sont sensibles : permissions privées, hors Git.
umask 077
mkdir -p terraform/cka/.runtime
terraform -chdir=terraform/cka plan -input=false \
  -var-file=../proxmox/credentials.auto.tfvars \
  -out=.runtime/create.tfplan
```

La première création attend sept ressources : un pool `CKA`, un stockage de
snippets dédié, l’image Ubuntu téléchargée et vérifiée, deux fichiers cloud-init
et deux VM. Vérifier que le plan ne remplace ni ne supprime une ressource
existante. Appliquer ensuite ce plan enregistré :

```sh
terraform -chdir=terraform/cka apply -input=false .runtime/create.tfplan
terraform -chdir=terraform/cka output -json lab
```

`-chdir` place Terraform dans `terraform/cka` ; le chemin `../proxmox/credentials.auto.tfvars`
réutilise donc le fichier existant de ce dépôt, sans en créer de copie. Le
provider reçoit `proxmox_api_url` et `proxmox_api_token` depuis ce fichier.
Sur le workspace actuel, son chemin absolu est
`/home/coder/projects/labops/terraform/proxmox/credentials.auto.tfvars`.

Le stack et son état local ont été déplacés depuis le checkout de travail
`labops-cka` vers ce répertoire le 1 novembre 2026. L’ancien chemin est un
lien local de compatibilité vers ce même répertoire : il ne possède aucun
état indépendant. L’état a été préservé, avec une sauvegarde privée dans
`.runtime/before-native-terraform-move.tfstate`. Sur un nouveau checkout,
restaurer l’état sauvegardé ici avant de planifier une infrastructure existante.
Un plan sans changement confirme la reprise des VM 620 et 621.

Le stockage `cka-snippets` utilise son propre répertoire
`/var/lib/vz/cka-snippets`. Le stack n’importe pas la définition du stockage
partagé `local` et ne change pas ses types de contenu. L’image `.img` est
stockée sous `local:iso/`, compatible avec Proxmox 8.3.

Après une interruption, conserver l’état et lancer un nouveau plan normal.
Ne pas repartir d’un état vide ni relancer un ancien plan après un changement
de clé/configuration. Si une ressource distante a été créée mais n’a pas été
enregistrée dans l’état, vérifier son identité et son contenu, puis effectuer
son import explicite ; ne pas écraser un objet existant de même nom.

Les modifications de cloud-init servent à la reconstruction. Elles ne
reconfigurent pas automatiquement les utilisateurs ou paquets d’un système
ayant déjà terminé son premier démarrage. Pour une rotation de clé sur des VM
existantes, installer et vérifier la nouvelle clé via l’accès administrateur,
mettre à jour la clé publique déclarée pour les reconstructions, puis retirer
l’ancienne clé. Une clé perdue doit être restaurée depuis la sauvegarde
chiffrée de l’opérateur ; elle ne se déduit pas de la clé publique.

## Accéder au lab depuis le projet CKA

Le provisionnement utilise directement Terraform. L’accès aux VM utilise
OpenSSH avec la clé privée correspondant à `keys/bingops.pub` :

```sh
cd /home/coder/projects/labops
terraform -chdir=terraform/cka output -json lab
# Terminal du master :
ssh -i ~/.ssh/homeops-proxmox -o IdentitiesOnly=yes ubuntu@192.168.10.20
# Dans un autre terminal, le worker :
ssh -i ~/.ssh/homeops-proxmox -o IdentitiesOnly=yes ubuntu@192.168.10.21
```

OpenSSH vérifie les clés d’hôte dans `~/.ssh/known_hosts`. À la première
connexion, vérifier l’empreinte avant de l’accepter ; après reconstruction,
vérifier la nouvelle identité avant de retirer l’ancienne entrée. Les clés
déjà vérifiées par l’ancien helper restent dans
`/home/coder/projects/cka/.runtime/lab/known_hosts` ; on peut les réutiliser avec
`-o UserKnownHostsFile=/home/coder/projects/cka/.runtime/lab/known_hosts`.

### Équivalent du port Vagrant 6443

La redirection est un tunnel SSH local, sans exposition d’un nouveau port sur
le nœud Proxmox :

```sh
ssh -i ~/.ssh/homeops-proxmox -o IdentitiesOnly=yes -N \
  -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:6443:192.168.60.20:6443 ubuntu@192.168.10.20
```

Le processus écoute sur `127.0.0.1:6443` et transfère vers
`192.168.60.20:6443` via le master. L’API répondra après l’installation de
Kubernetes. Adapter le `server` du kubeconfig client à ce point d’entrée et
conserver la vérification TLS : utiliser un nom présent dans les SAN du
certificat via `tls-server-name`, par exemple `k8s-master`, ou prévoir
`127.0.0.1` dans les SAN à l’initialisation. Ne pas utiliser
`insecure-skip-tls-verify` pour contourner une erreur de certificat.

### Équivalent du dossier VirtualBox partagé

Le master exporte `/opt/shared` au worker en NFSv4 sur le réseau du lab. Le
worker utilise une unité systemd d’automontage. Le dossier est accessible sous
le même chemin dans les deux VM, avec `root_squash` et l’utilisateur `ubuntu`.

Le dossier local `cka/shared/` est synchronisé explicitement avec le master :

```sh
cd /home/coder/projects/cka
rsync -az --no-owner --no-group \
  -e 'ssh -i ~/.ssh/homeops-proxmox -o IdentitiesOnly=yes' \
  shared/ ubuntu@192.168.10.20:/opt/shared/
# Pour rapatrier le partage :
rsync -az --no-owner --no-group \
  -e 'ssh -i ~/.ssh/homeops-proxmox -o IdentitiesOnly=yes' \
  ubuntu@192.168.10.20:/opt/shared/ shared/
```

Il ne s’agit pas d’un montage continu du home Coder : aucune infrastructure NFS
n’est ajoutée à l’hôte Proxmox. Les commandes n’utilisent pas `--delete`.
Rapatrier les fichiers utiles avant de détruire les VM.

## Vérification et récupération

Attendre la fin de `sudo cloud-init status --wait` sur chaque VM. Vérifier
ensuite hostname, deux interfaces, résolution des deux noms par `/etc/hosts`,
démarrage du guest agent, accès SSH avec la clé fournie et montage NFS du
worker. Les paquets Kubernetes doivent encore être absents. Un test de partage
peut créer un fichier temporaire dans `/opt/shared` sur le master, le lire sur
le worker et le supprimer après vérification.

Conserver le state local et ses backups avec des permissions 0600 dans le home
persistant et une sauvegarde chiffrée de l’opérateur. Ne pas exécuter le même
stack depuis deux copies indépendantes de l’état. Sans état, inventorier et
importer les ressources vérifiées avant un apply. Sans disque de VM, recréer
Ubuntu depuis Git et l’image épinglée ; restaurer les fichiers utiles depuis
`cka/shared/` ou une sauvegarde. Les exercices et installations Kubernetes
dans les VM ne sont pas reconstruits automatiquement.

Toute destruction nécessite une confirmation explicite des VM **620 et 621**
et de la perte de leurs disques. Un futur plan de destruction de ce stack
inclura aussi ses snippets, son image téléchargée, son stockage dédié et son
pool ; il ne doit jamais être exécuté sur le stack `terraform/proxmox`.

## Contrat de reconstruction

- Source de vérité : ce répertoire et sa version de provider verrouillée.
- Entrées externes : jeton API et clé SSH privée de l’opérateur, récupérés par
  les procédures liées ci-dessus ; aucun identifiant n’est affiché.
- État généré : state/plan Terraform, image téléchargée, VM et clés d’hôte SSH.
- Reprise : replan avec le même état ; import ciblé après vérification si une
  interruption a empêché l’enregistrement d’une ressource.
- Ordre : Proxmox + VLAN 10 → stack CKA → cloud-init → vérifications → exercices.
- Contrôles sûrs : `terraform output -json lab`, lecture des paramètres des VM,
  SSH, état cloud-init et tests de connectivité ; ne pas afficher le state.

Documentation primaire : [provider bpg 0.111.1](https://registry.terraform.io/providers/bpg/proxmox/0.111.1/docs),
[image Ubuntu épinglée et sommes](https://cloud-images.ubuntu.com/releases/jammy/release-20261020/SHA256SUMS).
