// ===============================================
// Bicep template for Foundry IQ knowledge bases
// Creates: Azure AI Search, Microsoft Foundry (with model deployments), Fabric capacity
// ===============================================

@description('Principal ID for role assignments (provided by azd)')
param principalId string

@description('Whether to deploy Fabric capacity')
param deployFabricCapacity bool = true

@description('User email/UPN for Fabric capacity administration')
param fabricAdminUpn string = ''

@description('Service principal object ID for Fabric capacity admin access')
param spPrincipalId string = ''

@description('The name prefix for all resources')
param resourcePrefix string = 'fiq'

@description('The location where all resources will be deployed')
param location string

@description('AI Search service SKU')
@allowed(['basic', 'standard', 'standard2', 'standard3', 'storage_optimized_l1', 'storage_optimized_l2'])
param searchServiceSku string = 'standard'

@description('Text embedding model name')
@allowed(['text-embedding-3-large'])
param embeddingModelName string = 'text-embedding-3-large'

@description('Text embedding model version')
param embeddingModelVersion string = '1'

@description('Embedding model deployment capacity')
@minValue(1)
@maxValue(200)
param embeddingModelCapacity int = 30

@description('Chat/reasoning model name')
param llmModelName string = 'gpt-5.4'

@description('Chat/reasoning model version')
param llmModelVersion string = '2026-03-05'

@description('Chat/reasoning model deployment capacity')
@minValue(1)
@maxValue(200)
param llmModelCapacity int = 50



// Variables for resource naming and configuration
var uniqueSuffix = uniqueString(resourceGroup().id)
var resourceNames = {
  searchService: '${resourcePrefix}-search-${uniqueSuffix}'
  searchIndex: '${resourcePrefix}-index'
  microsoftFoundry: '${resourcePrefix}-foundry-${uniqueSuffix}'
  microsoftFoundryProject: '${resourcePrefix}-project-${uniqueSuffix}'
  embeddingDeployment: 'text-embedding-3-large'
  llmDeployment: 'gpt-5.4'
}

// ===============================================
// AZURE AI SEARCH SERVICE
// ===============================================

@description('Azure AI Search service for vector search and document indexing')
resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: resourceNames.searchService
  location: 'westcentralus'
  sku: {
    name: searchServiceSku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    networkRuleSet: {
      ipRules: []
    }
    encryptionWithCmk: {
      enforcement: 'Unspecified'
    }
    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
    semanticSearch: 'standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
}

// ===============================================
// SERVICE PRINCIPAL ROLE ASSIGNMENTS
// ===============================================

// Search Index Data Contributor role for SP
resource SPuserSearchIndexContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(uniqueSuffix, 'sp-data-reader') 
  scope: searchService
  properties: {
    principalId: searchService.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  }
}

// Cognitive Services OpenAI User role for AI Search MI (subscription scope)
resource searchServiceToOpenAIRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, searchService.name, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    principalId: searchService.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  }
}

// Azure AI User role for AI Search MI (subscription scope)
resource searchServiceToAIUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, searchService.name, '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  properties: {
    principalId: searchService.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// Cognitive Services User role for AI Search MI (subscription scope)
resource searchServiceToCognitiveServicesUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, searchService.name, 'a97b65f3-24c7-4388-baec-2e87135dc908')
  properties: {
    principalId: searchService.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}

// ===============================================
// LAB USER ROLE ASSIGNMENTS
// ===============================================

// Search Service Contributor role for lab user
resource userSearchContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, searchService.name, principalId, '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
  scope: searchService
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
  }
}

// Search Index Data Reader role for lab user
resource userSearchIndexReaderRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, searchService.name, principalId, '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  scope: searchService
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  }
}

// Search Index Data Contributor role for lab user
resource userSearchIndexDataContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, searchService.name, principalId, '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  scope: searchService
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  }
}


// ===============================================
// MICROSOFT FOUNDRY (Account + Project)
// ===============================================

@description('Microsoft Foundry account')
resource microsoftFoundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: resourceNames.microsoftFoundry
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: resourceNames.microsoftFoundry
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}

@description('Microsoft Foundry project')
resource microsoftFoundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: microsoftFoundryAccount
  name: resourceNames.microsoftFoundryProject
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// Search Index Data Reader role for the Foundry project managed identity.
// This is required for KB MCP access when the project connection uses ProjectManagedIdentity.
resource microsoftFoundryProjectSearchIndexReaderRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, searchService.name, microsoftFoundryProject.id, '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  scope: searchService
  properties: {
    principalId: microsoftFoundryProject.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  }
}

// ===============================================
// MODEL DEPLOYMENTS (under Microsoft Foundry account)
// ===============================================

@description('Text embedding model deployment for vector generation')
resource embeddingModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: microsoftFoundryAccount
  name: resourceNames.embeddingDeployment
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingModelCapacity
  }
}

@description('Chat/reasoning model deployment for agentic retrieval')
resource llmModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: microsoftFoundryAccount
  name: resourceNames.llmDeployment
  properties: {
    model: {
      format: 'OpenAI'
      name: llmModelName
      version: llmModelVersion
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: llmModelCapacity
  }
  dependsOn: [
    embeddingModelDeployment
  ]
}

// Azure AI User role for lab user on Microsoft Foundry account (needed for Azure OpenAI API)
resource userMicrosoftFoundryAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(microsoftFoundryAccount.id, 'Azure AI User', principalId)
  scope: microsoftFoundryAccount
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// Azure AI Project Manager role for lab user on Microsoft Foundry account
resource userMicrosoftFoundryAccountProjectManagerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(microsoftFoundryAccount.id, 'Azure AI Project Manager', principalId)
  scope: microsoftFoundryAccount
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'eadc314b-1a2d-4efa-be10-5d325db5065e')
  }
}

// Azure AI User role for lab user on Microsoft Foundry project (needed for projects/agents API)
resource userMicrosoftFoundryProjectRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(microsoftFoundryProject.id, 'Azure AI User', principalId)
  scope: microsoftFoundryProject
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// Azure AI Project Manager role for lab user on Microsoft Foundry project (needed for agents/write)
resource userMicrosoftFoundryProjectManagerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(microsoftFoundryProject.id, 'Azure AI Project Manager', principalId)
  scope: microsoftFoundryProject
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'eadc314b-1a2d-4efa-be10-5d325db5065e')
  }
}

@description('Microsoft Foundry project endpoint in SDK format')
output MICROSOFT_FOUNDRY_PROJECT_ENDPOINT string = 'https://${microsoftFoundryAccount.name}.services.ai.azure.com/api/projects/${microsoftFoundryProject.name}'

@description('Microsoft Foundry project resource ID')
output MICROSOFT_FOUNDRY_PROJECT_ID string = microsoftFoundryProject.id

@description('Azure AI Search service endpoint')
output AZURE_SEARCH_SERVICE_ENDPOINT string = 'https://${searchService.name}.search.windows.net'

@description('Azure AI Search service name')
output AZURE_SEARCH_SERVICE_NAME string = searchService.name

@description('Azure OpenAI service endpoint (via Microsoft Foundry account)')
output AZURE_OPENAI_ENDPOINT string = microsoftFoundryAccount.properties.endpoint

@description('Azure OpenAI service name (Microsoft Foundry account)')
output AZURE_OPENAI_SERVICE_NAME string = microsoftFoundryAccount.name

@description('Text embedding model deployment name')
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = embeddingModelDeployment.name

@description('Chat model deployment name')
output AZURE_OPENAI_CHATGPT_DEPLOYMENT string = llmModelDeployment.name

// ===============================================
// MICROSOFT FABRIC CAPACITY
// ===============================================

@description('Microsoft Fabric capacity for lakehouse workloads')
resource fabricCapacity 'Microsoft.Fabric/capacities@2023-11-01' = if (deployFabricCapacity) {
  name: '${resourcePrefix}fabric${uniqueSuffix}'
  location: location
  sku: {
    name: 'F2'
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: empty(spPrincipalId) ? [
        empty(fabricAdminUpn) ? principalId : fabricAdminUpn
      ] : [
        empty(fabricAdminUpn) ? principalId : fabricAdminUpn
        spPrincipalId
      ]
    }
  }
}

@description('Fabric capacity name')
output FABRIC_CAPACITY_NAME string = deployFabricCapacity ? fabricCapacity.name : ''

@description('Fabric capacity resource ID')
output FABRIC_CAPACITY_ID string = deployFabricCapacity ? fabricCapacity.id : ''

@description('Azure tenant ID for deployment')
output AZURE_TENANT_ID string = tenant().tenantId
