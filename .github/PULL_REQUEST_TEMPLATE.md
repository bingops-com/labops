# 📡 Labops Pull Request Description

## 📋 Description

**Briefly describe the purpose of this PR**:

---

## ⚠️ Points of Attention

Are there any specific aspects that need extra attention?
- **Potential impacts on other features or services**: 
- **Breaking changes or migrations required**: 
- **Dependencies or external services involved**: 

---

## 🧪 How to Test

Procedure to test this PR:
1. Clone the branch and navigate to the project folder.
2. Run the following commands:
    ```sh
    export PROJECT_PATH="/opt/homeops/labops"
   
   # Deploy Terraform
    cd $PROJECT_PATH/terraform \
      && terraform init \
      && terraform plan
   
    # Deploy Ansible
    cd $PROJECT_PATH/ansible \
      && ansible-playbook site.yml --tags preprod -i inventories/main/hosts
    
   # Deploy Kustomize
    kubectl kustomize --enable-helm apps/xxx/clusters/preprod | kubectl apply -f -
    ```
3. Check if the new feature/fix works as expected.
4. Confirm that existing features are not impacted.

---

## 🚀 Deployment

Procedure to deploy this PR to production:
1. Merge this PR into the `master` branch.
2. Ensure the CI/CD pipeline completes successfully.
3. Deploy using the following command:
    ```sh
   # Update the master branch
    git checkout master \
      && git pull origin master

    export PROJECT_PATH="/opt/homeops/labops"
   
   # Deploy Terraform
    cd $PROJECT_PATH/terraform \
      && terraform init \
      && terraform apply

   # Deploy Ansible
    cd $PROJECT_PATH/ansible \
      && ansible-playbook site.yml --tags production -i inventories/main/hosts
   
   # Deploy Kustomize
    kubectl kustomize --enable-helm apps/xxx/clusters/production | kubectl apply -f -
    ```
4. Monitor logs and metrics for any issues.

---

## 🔗 Related Issues

- Closes issue : [#XX](https://github.com/bingops-com/labops/issues/XX)
- Related to issue : [#XX](https://github.com/bingops-com/labops/issues/XX)

---

## 🙏 Additional Notes

- **Anything else the reviewers should know**: 
- **Screenshots or GIFs to demonstrate the change**:
