#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from gabbi import fixture
from oslo_middleware import cors
from oslo_utils import uuidutils

from nova.api.openstack.placement import deploy
from nova.api.openstack.placement import exception
from nova.api.openstack.placement.objects import resource_provider as rp_obj
from nova import conf
from nova import config
from nova import context
from nova.tests import fixtures
from nova.tests import uuidsentinel as uuids


CONF = conf.CONF


def setup_app():
    return deploy.loadapp(CONF)


class APIFixture(fixture.GabbiFixture):
    """Setup the required backend fixtures for a basic placement service."""

    def __init__(self):
        self.conf = None

    def start_fixture(self):
        # Set up stderr and stdout captures by directly driving the
        # existing nova fixtures that do that. This captures the
        # output that happens outside individual tests (for
        # example database migrations).
        self.standard_logging_fixture = fixtures.StandardLogging()
        self.standard_logging_fixture.setUp()
        self.output_stream_fixture = fixtures.OutputStreamCapture()
        self.output_stream_fixture.setUp()

        self.conf = CONF
        self.conf.set_override('auth_strategy', 'noauth2', group='api')
        # Be explicit about all three database connections to avoid
        # potential conflicts with config on disk.
        self.conf.set_override('connection', "sqlite://", group='database')
        self.conf.set_override('connection', "sqlite://",
                               group='api_database')

        # Register CORS opts, but do not set config. This has the
        # effect of exercising the "don't use cors" path in
        # deploy.py. Without setting some config the group will not
        # be present.
        self.conf.register_opts(cors.CORS_OPTS, 'cors')

        # Make sure default_config_files is an empty list, not None.
        # If None /etc/nova/nova.conf is read and confuses results.
        config.parse_args([], default_config_files=[], configure_db=False,
                          init_rpc=False)

        # NOTE(cdent): The main database is not used but we still need to
        # manage it to make the fixtures work correctly and not cause
        # conflicts with other tests in the same process.
        self._reset_db_flags()
        self.api_db_fixture = fixtures.Database('api')
        self.main_db_fixture = fixtures.Database('main')
        self.api_db_fixture.reset()
        self.main_db_fixture.reset()

        os.environ['RP_UUID'] = uuidutils.generate_uuid()
        os.environ['RP_NAME'] = uuidutils.generate_uuid()
        os.environ['CUSTOM_RES_CLASS'] = 'CUSTOM_IRON_NFV'
        os.environ['PROJECT_ID'] = uuidutils.generate_uuid()
        os.environ['USER_ID'] = uuidutils.generate_uuid()
        os.environ['PROJECT_ID_ALT'] = uuidutils.generate_uuid()
        os.environ['USER_ID_ALT'] = uuidutils.generate_uuid()
        os.environ['INSTANCE_UUID'] = uuidutils.generate_uuid()
        os.environ['MIGRATION_UUID'] = uuidutils.generate_uuid()
        os.environ['CONSUMER_UUID'] = uuidutils.generate_uuid()
        os.environ['PARENT_PROVIDER_UUID'] = uuidutils.generate_uuid()
        os.environ['ALT_PARENT_PROVIDER_UUID'] = uuidutils.generate_uuid()

    def stop_fixture(self):
        self.api_db_fixture.cleanup()
        self.main_db_fixture.cleanup()

        # Since we clean up the DB, we need to reset the traits sync
        # flag to make sure the next run will recreate the traits and
        # reset the _RC_CACHE so that any cached resource classes
        # are flushed.
        self._reset_db_flags()

        self.output_stream_fixture.cleanUp()
        self.standard_logging_fixture.cleanUp()
        if self.conf:
            self.conf.reset()

    @staticmethod
    def _reset_db_flags():
        rp_obj._TRAITS_SYNCED = False
        rp_obj._RC_CACHE = None


class AllocationFixture(APIFixture):
    """An APIFixture that has some pre-made Allocations."""

    def start_fixture(self):
        super(AllocationFixture, self).start_fixture()
        self.context = context.get_admin_context()

        # For use creating and querying allocations/usages
        os.environ['ALT_USER_ID'] = uuidutils.generate_uuid()
        project_id = os.environ['PROJECT_ID']
        user_id = os.environ['USER_ID']
        alt_user_id = os.environ['ALT_USER_ID']

        # Stealing from the super
        rp_name = os.environ['RP_NAME']
        rp_uuid = os.environ['RP_UUID']
        rp = rp_obj.ResourceProvider(
            self.context, name=rp_name, uuid=rp_uuid)
        rp.create()

        # Create some DISK_GB inventory and allocations.
        consumer_id = uuidutils.generate_uuid()
        inventory = rp_obj.Inventory(
            self.context, resource_provider=rp,
            resource_class='DISK_GB', total=2048,
            step_size=10, min_unit=10, max_unit=600)
        inventory.obj_set_defaults()
        rp.add_inventory(inventory)
        alloc1 = rp_obj.Allocation(
            self.context, resource_provider=rp,
            resource_class='DISK_GB',
            consumer_id=consumer_id,
            project_id=project_id,
            user_id=user_id,
            used=500)
        alloc2 = rp_obj.Allocation(
            self.context, resource_provider=rp,
            resource_class='DISK_GB',
            consumer_id=consumer_id,
            project_id=project_id,
            user_id=user_id,
            used=500)
        alloc_list = rp_obj.AllocationList(
            self.context,
            objects=[alloc1, alloc2]
        )
        alloc_list.create_all()

        # Create some VCPU inventory and allocations.
        consumer_id = uuidutils.generate_uuid()
        os.environ['CONSUMER_ID'] = consumer_id
        inventory = rp_obj.Inventory(
            self.context, resource_provider=rp,
            resource_class='VCPU', total=10,
            max_unit=4)
        inventory.obj_set_defaults()
        rp.add_inventory(inventory)
        alloc1 = rp_obj.Allocation(
            self.context, resource_provider=rp,
            resource_class='VCPU',
            consumer_id=consumer_id,
            project_id=project_id,
            user_id=user_id,
            used=2)
        alloc2 = rp_obj.Allocation(
            self.context, resource_provider=rp,
            resource_class='VCPU',
            consumer_id=consumer_id,
            project_id=project_id,
            user_id=user_id,
            used=4)
        alloc_list = rp_obj.AllocationList(
                self.context,
                objects=[alloc1, alloc2])
        alloc_list.create_all()

        # Create a couple of allocations for a different user.
        consumer_id = uuidutils.generate_uuid()
        alloc1 = rp_obj.Allocation(
            self.context, resource_provider=rp,
            resource_class='DISK_GB',
            consumer_id=consumer_id,
            project_id=project_id,
            user_id=alt_user_id,
            used=20)
        alloc2 = rp_obj.Allocation(
            self.context, resource_provider=rp,
            resource_class='VCPU',
            consumer_id=consumer_id,
            project_id=project_id,
            user_id=alt_user_id,
            used=1)
        alloc_list = rp_obj.AllocationList(
                self.context,
                objects=[alloc1, alloc2])
        alloc_list.create_all()

        # The ALT_RP_XXX variables are for a resource provider that has
        # not been created in the Allocation fixture
        os.environ['ALT_RP_UUID'] = uuidutils.generate_uuid()
        os.environ['ALT_RP_NAME'] = uuidutils.generate_uuid()


class SharedStorageFixture(APIFixture):
    """An APIFixture that has some two compute nodes without local storage
    associated by aggregate to a provider of shared storage.
    """

    def start_fixture(self):
        super(SharedStorageFixture, self).start_fixture()
        self.context = context.get_admin_context()

        cn1_uuid = uuidutils.generate_uuid()
        cn2_uuid = uuidutils.generate_uuid()
        ss_uuid = uuidutils.generate_uuid()
        agg_uuid = uuidutils.generate_uuid()
        os.environ['CN1_UUID'] = cn1_uuid
        os.environ['CN2_UUID'] = cn2_uuid
        os.environ['SS_UUID'] = ss_uuid
        os.environ['AGG_UUID'] = agg_uuid

        cn1 = rp_obj.ResourceProvider(
            self.context,
            name='cn1',
            uuid=cn1_uuid)
        cn1.create()

        cn2 = rp_obj.ResourceProvider(
            self.context,
            name='cn2',
            uuid=cn2_uuid)
        cn2.create()

        ss = rp_obj.ResourceProvider(
            self.context,
            name='ss',
            uuid=ss_uuid)
        ss.create()

        # Populate compute node inventory for VCPU and RAM
        for cn in (cn1, cn2):
            vcpu_inv = rp_obj.Inventory(
                self.context,
                resource_provider=cn,
                resource_class='VCPU',
                total=24,
                reserved=0,
                max_unit=24,
                min_unit=1,
                step_size=1,
                allocation_ratio=16.0)
            vcpu_inv.obj_set_defaults()
            ram_inv = rp_obj.Inventory(
                self.context,
                resource_provider=cn,
                resource_class='MEMORY_MB',
                total=128 * 1024,
                reserved=0,
                max_unit=128 * 1024,
                min_unit=256,
                step_size=256,
                allocation_ratio=1.5)
            ram_inv.obj_set_defaults()
            inv_list = rp_obj.InventoryList(objects=[vcpu_inv, ram_inv])
            cn.set_inventory(inv_list)

        t_avx_sse = rp_obj.Trait.get_by_name(self.context, "HW_CPU_X86_SSE")
        t_avx_sse2 = rp_obj.Trait.get_by_name(self.context, "HW_CPU_X86_SSE2")
        cn1.set_traits(rp_obj.TraitList(objects=[t_avx_sse, t_avx_sse2]))

        # Populate shared storage provider with DISK_GB inventory
        disk_inv = rp_obj.Inventory(
            self.context,
            resource_provider=ss,
            resource_class='DISK_GB',
            total=2000,
            reserved=100,
            max_unit=2000,
            min_unit=10,
            step_size=10,
            allocation_ratio=1.0)
        disk_inv.obj_set_defaults()
        inv_list = rp_obj.InventoryList(objects=[disk_inv])
        ss.set_inventory(inv_list)

        # Mark the shared storage pool as having inventory shared among any
        # provider associated via aggregate
        t = rp_obj.Trait.get_by_name(
            self.context,
            "MISC_SHARES_VIA_AGGREGATE",
        )
        ss.set_traits(rp_obj.TraitList(objects=[t]))

        # Now associate the shared storage pool and both compute nodes with the
        # same aggregate
        cn1.set_aggregates([agg_uuid])
        cn2.set_aggregates([agg_uuid])
        ss.set_aggregates([agg_uuid])


class NonSharedStorageFixture(APIFixture):
    """An APIFixture that has two compute nodes with local storage that do not
    use shared storage.
    """
    def start_fixture(self):
        super(NonSharedStorageFixture, self).start_fixture()
        self.context = context.get_admin_context()

        cn1_uuid = uuidutils.generate_uuid()
        cn2_uuid = uuidutils.generate_uuid()
        aggA_uuid = uuidutils.generate_uuid()
        aggB_uuid = uuidutils.generate_uuid()
        aggC_uuid = uuidutils.generate_uuid()
        os.environ['CN1_UUID'] = cn1_uuid
        os.environ['CN2_UUID'] = cn2_uuid
        os.environ['AGGA_UUID'] = aggA_uuid
        os.environ['AGGB_UUID'] = aggB_uuid
        os.environ['AGGC_UUID'] = aggC_uuid

        cn1 = rp_obj.ResourceProvider(
            self.context,
            name='cn1',
            uuid=cn1_uuid)
        cn1.create()

        cn2 = rp_obj.ResourceProvider(
            self.context,
            name='cn2',
            uuid=cn2_uuid)
        cn2.create()

        # Populate compute node inventory for VCPU and RAM
        for cn in (cn1, cn2):
            vcpu_inv = rp_obj.Inventory(
                self.context,
                resource_provider=cn,
                resource_class='VCPU',
                total=24,
                reserved=0,
                max_unit=24,
                min_unit=1,
                step_size=1,
                allocation_ratio=16.0)
            vcpu_inv.obj_set_defaults()
            ram_inv = rp_obj.Inventory(
                self.context,
                resource_provider=cn,
                resource_class='MEMORY_MB',
                total=128 * 1024,
                reserved=0,
                max_unit=128 * 1024,
                min_unit=256,
                step_size=256,
                allocation_ratio=1.5)
            ram_inv.obj_set_defaults()
            disk_inv = rp_obj.Inventory(
                self.context,
                resource_provider=cn,
                resource_class='DISK_GB',
                total=2000,
                reserved=100,
                max_unit=2000,
                min_unit=10,
                step_size=10,
                allocation_ratio=1.0)
            disk_inv.obj_set_defaults()
            inv_list = rp_obj.InventoryList(objects=[vcpu_inv, ram_inv,
                    disk_inv])
            cn.set_inventory(inv_list)


class CORSFixture(APIFixture):
    """An APIFixture that turns on CORS."""

    def start_fixture(self):
        super(CORSFixture, self).start_fixture()
        # NOTE(cdent): If we remove this override, then the cors
        # group ends up not existing in the conf, so when deploy.py
        # wants to load the CORS middleware, it will not.
        self.conf.set_override('allowed_origin', 'http://valid.example.com',
                               group='cors')


# TODO(efried): Common with test_allocation_candidates
def _add_inventory(rp, rc, total, **kwargs):
    kwargs.setdefault('max_unit', total)
    inv = rp_obj.Inventory(rp._context, resource_provider=rp,
                           resource_class=rc, total=total, **kwargs)
    inv.obj_set_defaults()
    rp.add_inventory(inv)


# TODO(efried): Common with test_allocation_candidates
def _set_traits(rp, *traits):
    tlist = []
    for tname in traits:
        try:
            trait = rp_obj.Trait.get_by_name(rp._context, tname)
        except exception.TraitNotFound:
            trait = rp_obj.Trait(rp._context, name=tname)
            trait.create()
        tlist.append(trait)
    rp.set_traits(rp_obj.TraitList(objects=tlist))


class GranularFixture(APIFixture):
    """An APIFixture that sets up the following provider environment for
    testing granular resource requests.

+========================++========================++========================+
|cn_left                 ||cn_middle               ||cn_right                |
|VCPU: 8                 ||VCPU: 8                 ||VCPU: 8                 |
|MEMORY_MB: 4096         ||MEMORY_MB: 4096         ||MEMORY_MB: 4096         |
|DISK_GB: 500            ||SRIOV_NET_VF: 8         ||DISK_GB: 500            |
|VGPU: 8                 ||CUSTOM_NET_MBPS: 4000   ||VGPU: 8                 |
|SRIOV_NET_VF: 8         ||traits: HW_CPU_X86_AVX, ||  - max_unit: 2         |
|CUSTOM_NET_MBPS: 4000   ||        HW_CPU_X86_AVX2,||traits: HW_CPU_X86_MMX, |
|traits: HW_CPU_X86_AVX, ||        HW_CPU_X86_SSE, ||        HW_GPU_API_DXVA,|
|        HW_CPU_X86_AVX2,||        HW_NIC_ACCEL_TLS||        CUSTOM_DISK_SSD,|
|        HW_GPU_API_DXVA,|+=+=====+================++==+========+============+
|        HW_NIC_DCB_PFC, |  :     :                    :        : a
|        CUSTOM_FOO      +..+     +--------------------+        : g
+========================+  : a   :                             : g
                            : g   :                             : C
+========================+  : g   :             +===============+======+
|shr_disk_1              |  : A   :             |shr_net               |
|DISK_GB: 1000           +..+     :             |SRIOV_NET_VF: 16      |
|traits: CUSTOM_DISK_SSD,|  :     : a           |CUSTOM_NET_MBPS: 40000|
|  MISC_SHARES_VIA_AGG...|  :     : g           |traits: MISC_SHARES...|
+========================+  :     : g           +======================+
+=======================+   :     : B
|shr_disk_2             +...+     :
|DISK_GB: 1000          |         :
|traits: MISC_SHARES... +.........+
+=======================+
    """
    def _create_provider(self, name, *aggs, **kwargs):
        # TODO(efried): Common with test_allocation_candidates.ProviderDBBase
        parent = kwargs.get('parent')
        rp = rp_obj.ResourceProvider(self.ctx, name=name,
                                     uuid=getattr(uuids, name))
        if parent:
            rp.parent_provider_uuid = parent
        rp.create()
        if aggs:
            rp.set_aggregates(aggs)
        return rp

    def start_fixture(self):
        super(GranularFixture, self).start_fixture()
        self.ctx = context.get_admin_context()

        rp_obj.ResourceClass(context=self.ctx, name='CUSTOM_NET_MBPS').create()

        os.environ['AGGA'] = uuids.aggA
        os.environ['AGGB'] = uuids.aggB
        os.environ['AGGC'] = uuids.aggC

        cn_left = self._create_provider('cn_left', uuids.aggA)
        os.environ['CN_LEFT'] = cn_left.uuid
        _add_inventory(cn_left, 'VCPU', 8)
        _add_inventory(cn_left, 'MEMORY_MB', 4096)
        _add_inventory(cn_left, 'DISK_GB', 500)
        _add_inventory(cn_left, 'VGPU', 8)
        _add_inventory(cn_left, 'SRIOV_NET_VF', 8)
        _add_inventory(cn_left, 'CUSTOM_NET_MBPS', 4000)
        _set_traits(cn_left, 'HW_CPU_X86_AVX', 'HW_CPU_X86_AVX2',
                    'HW_GPU_API_DXVA', 'HW_NIC_DCB_PFC', 'CUSTOM_FOO')

        cn_middle = self._create_provider('cn_middle', uuids.aggA, uuids.aggB)
        os.environ['CN_MIDDLE'] = cn_middle.uuid
        _add_inventory(cn_middle, 'VCPU', 8)
        _add_inventory(cn_middle, 'MEMORY_MB', 4096)
        _add_inventory(cn_middle, 'SRIOV_NET_VF', 8)
        _add_inventory(cn_middle, 'CUSTOM_NET_MBPS', 4000)
        _set_traits(cn_middle, 'HW_CPU_X86_AVX', 'HW_CPU_X86_AVX2',
                    'HW_CPU_X86_SSE', 'HW_NIC_ACCEL_TLS')

        cn_right = self._create_provider('cn_right', uuids.aggB, uuids.aggC)
        os.environ['CN_RIGHT'] = cn_right.uuid
        _add_inventory(cn_right, 'VCPU', 8)
        _add_inventory(cn_right, 'MEMORY_MB', 4096)
        _add_inventory(cn_right, 'DISK_GB', 500)
        _add_inventory(cn_right, 'VGPU', 8, max_unit=2)
        _set_traits(cn_right, 'HW_CPU_X86_MMX', 'HW_GPU_API_DXVA',
                    'CUSTOM_DISK_SSD')

        shr_disk_1 = self._create_provider('shr_disk_1', uuids.aggA)
        os.environ['SHR_DISK_1'] = shr_disk_1.uuid
        _add_inventory(shr_disk_1, 'DISK_GB', 1000)
        _set_traits(shr_disk_1, 'MISC_SHARES_VIA_AGGREGATE', 'CUSTOM_DISK_SSD')

        shr_disk_2 = self._create_provider(
            'shr_disk_2', uuids.aggA, uuids.aggB)
        os.environ['SHR_DISK_2'] = shr_disk_2.uuid
        _add_inventory(shr_disk_2, 'DISK_GB', 1000)
        _set_traits(shr_disk_2, 'MISC_SHARES_VIA_AGGREGATE')

        shr_net = self._create_provider('shr_net', uuids.aggC)
        os.environ['SHR_NET'] = shr_net.uuid
        _add_inventory(shr_net, 'SRIOV_NET_VF', 16)
        _add_inventory(shr_net, 'CUSTOM_NET_MBPS', 40000)
        _set_traits(shr_net, 'MISC_SHARES_VIA_AGGREGATE')
