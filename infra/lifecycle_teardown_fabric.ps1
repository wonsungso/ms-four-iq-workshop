# Delete Fabric capacity in the resource group to release regional quota.
# Without this, unused capacities from ended lab sessions accumulate and block
# future deployments once the quota ceiling is reached.
$resourceGroupName = "@lab.CloudResourceGroup(LAB532Final-ResourceGroup).Name"
$fabricCapacities = Get-AzResource -ResourceGroupName $resourceGroupName -ResourceType "Microsoft.Fabric/capacities"
foreach ($fc in $fabricCapacities) {
    Remove-AzResource -ResourceId $fc.ResourceId -Force
    Write-Output "Deleted Fabric capacity: $($fc.Name)"
}
