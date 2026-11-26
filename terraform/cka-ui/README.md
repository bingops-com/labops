> Contrôleur retiré du workspace le 3 novembre 2026. Le code actif est
> https://github.com/bingops-com/cka/tree/main/controller et le seul état actif
> appartient au PVC cka/cka-controller en production. Le processus local est
> arrêté et bloqué par .runtime/ownership-moved. Ne pas réinitialiser cet état.
> Voir https://github.com/bingops-com/cka/blob/main/docs/production.md.

# Labs CKA créés par scénario

Ce stack possède exclusivement les labs jetables lancés depuis le projet
[CKA](../../../cka/README.md). L’utilisateur choisit un exercice ; le contrôleur
lit ses prérequis dans scenarios.json. L’API refuse les nombres de nœuds et les
profils fournis par le navigateur. Le provisionnement, l’injection du cas et la
vérification de son état initial sont automatiques. La vue candidat ne reçoit
ni préparation, ni indices, ni correction, ni détail des opérations internes.

## Propriétaires et périmètre

- terraform/cka conserve l’état des anciens VM 620/621. Leur retrait nécessite
  leur confirmation explicite et utilise un plan ciblé de ce stack.
- terraform/cka-ui possède le pool CKA-UI, ses snippets et image, la passerelle
  700, les control planes 710–712 et les workers 720–722.
- runner/host-network.sh possède uniquement vmbr90, sans port physique ni IP
  hôte, et les chaînes CKA_UI_INPUT/CKA_UI_FORWARD IPv4/IPv6. Son installation
  est idempotente et refuse un bridge existant sans marqueur de propriété.
- Les VM d’exercice ont une seule interface sur vmbr90. La passerelle 700 a
  aussi une interface VLAN 10, 192.168.10.22 ; elle n’est jamais une cible du
  terminal candidat. Elle fournit NAT et répartition API, en refusant les
  destinations privées et l’accès SSH depuis les VM d’exercice.
- Aucun objet Talos/CAPI, labmgmt, labprod, stockage de production ou service
  GitOps n’appartient à ce stack. Ne pas lier ses états à terraform/proxmox.

L’adresse de passerelle, le bridge, le stockage et la plage VM sont des
prérequis réservés par l’opérateur Proxmox. Ils doivent être libres avant la
première création ; ne pas réutiliser un objet inconnu de même nom.

## Entrées, état et reconstruction

Le jeton API est lu directement depuis le fichier ignoré
../proxmox/credentials.auto.tfvars ; aucune copie n’est faite dans le projet web.
Sa création, ses droits et sa récupération depuis le gestionnaire de secrets
sont décrits dans le [runbook Proxmox](../proxmox/README.md#create-the-terraform-api-token).
La clé SSH opérateur reste ~/.ssh/homeops-proxmox ; sa récupération appartient
à [l’enrôlement du workspace](../../hacks/README.md). Le contrôleur actuel reste
réservé au propriétaire du workspace ; il ne fournit pas d’identité multi-user.

La CA publique Proxmox, vérifiée par l’accès SSH opérateur dont la clé hôte
est épinglée, est enregistrée dans .runtime/proxmox-ca.pem. Le certificat ne
remplace pas un jeton. Vérification de chaîne et de nom conservée ; le client
Python désactive uniquement le contrôle strict des extensions de l’ancienne CA
PVE 8. Ne pas désactiver TLS ni accepter des clés SSH invitées à l’aveugle.

.runtime contient l’inventaire SQLite, le verrou du contrôleur, les identités
SSH éphémères, les configurations de connexion, plans et diagnostics privés.
terraform.tfstate et .terraform.lock.hcl appartiennent à ce stack : conserver
le state privé dans les sauvegardes du home retenu ; le lockfile de provider
est une source à versionner. Les clés invitées sont générées par session et
épinglées via le guest agent après vérification du VMID, du nom et de
l’identifiant de session dans la configuration Proxmox.

Ordre de reconstruction : Proxmox + VLAN 10 + stockages → récupération des
entrées opérateur et du state → initialisation du provider verrouillé →
contrôleur → choix d’exercice → bridge et garde hôte → passerelle → vérifications
→ VM d’exercice → isolation → kubeadm/Calico → scénario → état initial vérifié.

Ne pas repartir d’un state vide si les ressources existent. Après interruption,
le contrôleur conserve la réservation et signale une intervention nécessaire.
Comparer inventaire, state et identifiant du lab avant toute reprise ; ne pas
relancer une création sur un environnement partiel. Les objets dont la
propriété n’est pas établie bloquent la création et ne sont jamais supprimés
automatiquement.

## Versions et contrôles

Ubuntu Server 22.04 release-20261020 et son SHA-256 sont déclarés dans main.tf.
Kubeadm, kubelet et kubectl sont épinglés à 1.37.2-1.1 ; cri-tools à 1.36.0-1.1
est installé explicitement. Containerd provient de
l’archive Ubuntu signée. Calico 3.33.0 est téléchargé avec son SHA-256 vérifié,
son CIDR Pod est explicite. Ces paquets et le manifeste amont ont été vérifiés
le 3 novembre 2026. Les dépendances Ubuntu restent celles de l’archive à la
date d’installation ; cette partie n’est pas une image système immuable.

Contrôles locaux sans accès aux invités :

- terraform fmt -check et terraform validate après init.
- python3 -m unittest discover -s tests -v.
- bash -n runner/host-network.sh templates/*.sh.
- python3 -m py_compile runner/*.py templates/check-scenario.py.

Contrôles réels avant annonce « prêt » : cloud-init terminé ; identités des VM
et SSH vérifiées ; refus vers hyperviseur, administration, production et
métadonnées, y compris après route directe usurpée depuis root ; registre images
accessible ; tous les nœuds et CNI prêts ; état initial du scénario non résolu.
Le contrôle réseau IPv6 comprend le garde hôte et l’absence de sortie IPv6
sur la passerelle ; les tests automatisés d’attaque invité actuels couvrent
principalement IPv4. Une VM ne garantit pas l’absence de faille hyperviseur.

## Exploitation propriétaire

Le serveur Next parle uniquement au socket Unix privé mode 0600. Le contrôleur
lit les secrets, exécute Terraform par argv, et transmet les commandes candidat
uniquement au shell de la VM attribuée. Il ne publie aucun endpoint TCP.

Lancer le contrôleur depuis une session persistante du workspace après les
contrôles locaux :

    python3 runner/control.py --enable-actions

Le fichier runner/control.py accepte des chemins opérateur explicites pour
le socket, le runtime, la CA et les credentials ; ces chemins ne peuvent pas
être fournis depuis l’application. Deux contrôleurs ne peuvent pas posséder
le même runtime. Le processus et le serveur Next restent des processus du
workspace ; ils doivent être relancés après remplacement de son conteneur.
Aucun redéploiement Kubernetes n’est nécessaire.

GET /api/lab montre l’inventaire attribué et un état générique. POST /api/lab
avec action=create accepte uniquement un identifiant de scénario autorisé.
Les opérations sont enregistrées durablement ; un seul lab peut être réservé,
actif, en erreur ou en suppression. Fermer l’onglet ne libère rien. Terminer
et évaluer clôt la tentative et expose ses critères de résultat.

La destruction utilise une modale indiquant les VMID et la perte des disques,
avec les boutons Annuler et Supprimer le lab. Aucune saisie n’est demandée.
Le clic transmet labId et une confirmation dérivée des VMID triés affichés ;
le serveur recalcule ce périmètre et refuse une confirmation devenue obsolète. Le verrou n’est
libéré qu’après vérification d’absence des VM. Les clés éphémères sont ensuite
retirées ; les diagnostics et state sont conservés pour la récupération.
L’image vérifiée, le pool, le stockage de snippets et le bridge/garde hôte sont
conservés comme infrastructure partagée de ce stack. Le plan de destruction
refuse toute suppression de ces objets communs ; seuls les VM et snippets de
la session sont ciblés. Cela évite de retélécharger l’image à chaque exercice.

La console actuelle exécute des commandes réelles non interactives, limitées
à 25 secondes. Un terminal PTY avec éditeur interactif et un examen blanc
multi-clusters ne sont pas encore implémentés ; ne pas présenter la console
comme une reproduction complète de l’examen.

## Références

- [Installation kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)
- [Prérequis Calico](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements)
- [Programme CKA](https://www.cncf.io/training/certification/cka/)

## Reprise non destructive d’une création

L’action opérateur retry, avec labId, est réservée aux créations interrompues
ou en erreur. Elle conserve l’identité et les VMID, vérifie les identités
réelles, puis réapplique le garde réseau et démarre uniquement les VM attribuées qui
sont arrêtées. Les identités sont revérifiées avant chaque démarrage. La reprise
n’utilise aucun appel Terraform, redémarrage forcé, remplacement ou reset du
cluster. Cela couvre un redémarrage externe de l’hyperviseur : on_boot reste
désactivé pour les VM d’exercice et le contrôleur reprend la même session. Une topologie différente,
une tentative clôturée ou une préparation partielle du scénario refuse la
reprise. Le marqueur scenario-started/ready dans le runtime empêche une seconde
injection silencieuse. Un cluster partiellement joint reste réservé jusqu’à
diagnostic. Ne jamais supprimer le runtime pour contourner cette réservation.

## Vérification du contrat de reconstruction

1. Un nouvel opérateur peut reconstruire depuis ce répertoire et les runbooks
   liés, après récupération des entrées sensibles et de l’état privé.
2. Le jeton API et la clé privée ne sont pas récupérables depuis Git : leur
   récupération et rotation appartiennent aux runbooks Proxmox et d’enrôlement.
3. Le bridge, l’image et le provisionnement déclaratif sont réconciliables ;
   une création interrompue conserve sa réservation. Les marqueurs de scénario
   empêchent de réinjecter une panne sur un état partiel ou déjà livré.
4. Terraform/cka possède les anciennes VM ; terraform/cka-ui possède les
   nouvelles. L’ordre de création et la persistance des ressources communes
   sont décrits ci-dessus. Aucun propriétaire Talos/CAPI n’est modifié.
5. Inventaire API filtré, état générique du contrôleur, contrôles d’identité,
   vérifications réseau et tests d’état permettent une vérification sans
   afficher les secrets, plans bruts ni fichiers de configuration privés.

Les nouveaux fichiers doivent être inclus dans la prochaine publication Git
du dépôt ; aucun push ni réconciliation GitOps n’est déclenché par le
contrôleur. Les processus du workspace et ressources du lab peuvent être
appliqués depuis cette copie de travail avant cette publication.

Avant toute injection de scénario, le contrôleur vérifie aussi les rollouts
Calico/CoreDNS et des échanges DNS, Service HTTP et Pod-à-Pod entre tous les
workers. Les Pods de contrôle restent dans cka-platform-check, namespace
réservé au diagnostic de l’environnement, jusqu’à la suppression de la session.
Ils n’indiquent pas la cause de la panne du scénario.

## Extractions des images et arrêt brutal

Le bootstrap impose OverlayFS et active la synchronisation du système de
fichiers lors des téléchargements CRI. Le chemin local de téléchargement est
explicite pour containerd 2.x, afin que cette synchronisation soit prise en
compte. Ce choix réduit le risque de snapshots partiellement persistés après
un arrêt brutal. Il ne constitue pas une preuve de la cause du dernier échec
du worker. Les contrôles fonctionnels bloquent l’ouverture tant que le réseau
et les composants système du cluster ne sont pas opérationnels.

Source primaire : https://github.com/containerd/containerd/blob/main/internal/cri/config/config.go
