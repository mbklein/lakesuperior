import pytest

from shutil import rmtree

from rdflib import Namespace, URIRef

from lakesuperior.store_layouts.ldp_rs.lmdb_store import LmdbStore, TxnManager


@pytest.fixture(scope='class')
def store():
    store = LmdbStore('/tmp/test_lmdbstore')
    yield store
    store.close()
    rmtree('/tmp/test_lmdbstore')


@pytest.mark.usefixtures('store')
class TestStoreInit:
    '''
    Tests for intializing and shutting down store and transactions.
    '''
    def test_open_close(self, store):
        '''
        Test opening and closing a store.
        '''
        tmpstore = LmdbStore('/tmp/test_lmdbstore_init')
        assert tmpstore.is_open
        tmpstore.close()
        assert not tmpstore.is_open


    def test_txn(self, store):
        '''
        Test opening and closing the main transaction.
        '''
        store.begin(True)
        assert store.is_txn_open
        store.commit()
        assert not store.is_txn_open
        store.begin(True)
        store.rollback()
        assert not store.is_txn_open


    def test_ctx_mgr(self, store):
        '''
        Test enclosing a transaction in a context.
        '''
        with TxnManager(store) as txn:
            pass
        assert not store.is_txn_open

        with TxnManager(store) as txn:
            raise RuntimeError
        assert not store.is_txn_open


    def test_rollback(self, store):
        '''
        Test rolling back a transaction.
        '''
        with TxnManager(store, True) as txn:
            store.add((
                URIRef('urn:nogo:s'), URIRef('urn:nogo:p'),
                URIRef('urn:nogo:o')))
            raise RuntimeError # This should roll back the transaction.

        with TxnManager(store) as txn:
            res = set(store.triples((None, None, None)))
        assert len(res) == 0


@pytest.mark.usefixtures('store')
class TestBasicOps:
    '''
    High-level tests for basic operations.
    '''
    def test_create_triple(self, store):
        '''
        Test creation of a single triple.
        '''
        trp = (
            URIRef('urn:test:s'), URIRef('urn:test:p'), URIRef('urn:test:o'))
        with TxnManager(store, True) as txn:
            store.add(trp)

            #import pdb; pdb.set_trace()
            res1 = set(store.triples((None, None, None)))
            res2 = set(store.triples(trp))
            assert len(res1) == 1
            assert len(res2) == 1
            assert trp in res1 & res2


    def test_triple_match_1bound(self, store):
        '''
        Test triple patterns matching one bound term.
        '''
        with TxnManager(store) as txn:
            res1 = set(store.triples((URIRef('urn:test:s'), None, None)))
            res2 = set(store.triples((None, URIRef('urn:test:p'), None)))
            res3 = set(store.triples((None, None, URIRef('urn:test:o'))))
            assert res1 == {(
                URIRef('urn:test:s'), URIRef('urn:test:p'),
                URIRef('urn:test:o'))}
            assert res2 == res1
            assert res3 == res2


    def test_triple_match_2bound(self, store):
        '''
        Test triple patterns matching two bound terms.
        '''
        with TxnManager(store) as txn:
            res1 = set(store.triples(
                (URIRef('urn:test:s'), URIRef('urn:test:p'), None)))
            res2 = set(store.triples(
                (URIRef('urn:test:s'), None, URIRef('urn:test:o'))))
            res3 = set(store.triples(
                (None, URIRef('urn:test:p'), URIRef('urn:test:o'))))
            assert res1 == {(
                URIRef('urn:test:s'), URIRef('urn:test:p'), URIRef('urn:test:o'))}
            assert res2 == res1
            assert res3 == res2


    def test_triple_no_match(self, store):
        '''
        Test various mismatches.
        '''
        with TxnManager(store, True) as txn:
            store.add((
                URIRef('urn:test:s'),
                URIRef('urn:test:p2'), URIRef('urn:test:o2')))
            store.add((
                URIRef('urn:test:s3'),
                URIRef('urn:test:p3'), URIRef('urn:test:o3')))
            res1 = set(store.triples((None, None, None)))
            assert len(res1) == 3

            res1 = set(store.triples(
                (URIRef('urn:test:s2'), URIRef('urn:test:p'), None)))
            res2 = set(store.triples(
                (URIRef('urn:test:s3'), None, URIRef('urn:test:o'))))
            res3 = set(store.triples(
                (None, URIRef('urn:test:p3'), URIRef('urn:test:o2'))))

            assert len(res1) == len(res2) == len(res3) == 0


    def test_remove(self, store):
        '''
        Test removing one or more triples.
        '''
        with TxnManager(store, True) as txn:
            store.remove((URIRef('urn:test:s3'),
                    URIRef('urn:test:p3'), URIRef('urn:test:o3')))

            res1 = set(store.triples((None, None, None)))
            assert len(res1) == 2

            store.remove((URIRef('urn:test:s'), None, None))
            res2 = set(store.triples((None, None, None)))
            assert len(res2) == 0


@pytest.mark.usefixtures('store')
class TestBindings:
    '''
    Tests for namespace bindings.
    '''
    @pytest.fixture
    def bindings(self):
        return (
            ('ns1', Namespace('http://test.org/ns#')),
            ('ns2', Namespace('http://my_org.net/ns#')),
            ('ns3', Namespace('urn:test:')),
            ('ns4', Namespace('info:myinst/graph#')),
        )


    def test_ns(self, store, bindings):
        '''
        Test namespace bindings.
        '''
        with TxnManager(store, True) as txn:
            for b in bindings:
                store.bind(*b)

            nslist = list(store.namespaces())
            assert len(nslist) == len(bindings)

            for i in range(len(bindings)):
                assert nslist[i] == bindings[i]


    def test_ns2pfx(self, store, bindings):
        '''
        Test namespace to prefix conversion.
        '''
        with TxnManager(store, True) as txn:
            for b in bindings:
                pfx, ns = b
                assert store.namespace(pfx) == ns


    def test_pfx2ns(self, store, bindings):
        '''
        Test namespace to prefix conversion.
        '''
        with TxnManager(store, True) as txn:
            for b in bindings:
                pfx, ns = b
                assert store.prefix(ns) == pfx


@pytest.mark.usefixtures('store')
class TestContext:
    '''
    Tests for context handling.
    '''
    # Add empty graph
    # Query graph → return graph
    # Add triples to graph
    # Query triples in graph → triples
    # Query triples in default graph → no results
    # Add another empty graph
    # Delete graph with triples
    # Query graph → no results
    # Query triples → no results
    # Delete empty graph
    # Query graph → no results
    def test_add_graph(self, store):
        '''
        Test creating an empty and a non-empty graph.
        '''
        gr_uri = URIRef('urn:bogus:graph#a')

        with TxnManager(store, True) as txn:
            store.add_graph(gr_uri)
            assert gr_uri in store.contexts()

    def test_add_trp_to_ctx(self, store):
        '''
        Test adding triples to a graph.
        '''
        gr_uri = URIRef('urn:bogus:graph#a') # From previous test
        gr2_uri = URIRef('urn:bogus:graph#b') # Never created before
        trp1 = (URIRef('urn:s:1'), URIRef('urn:p:1'), URIRef('urn:o:1'))
        trp2 = (URIRef('urn:s:2'), URIRef('urn:p:2'), URIRef('urn:o:2'))
        trp3 = (URIRef('urn:s:3'), URIRef('urn:p:3'), URIRef('urn:o:3'))

        with TxnManager(store, True) as txn:
            store.add(trp1, gr_uri)
            store.add(trp2, gr_uri)
            store.add(trp2, store.DEFAULT_GRAPH_URI)
            store.add(trp3, gr2_uri)
            store.add(trp3)

            assert len(set(store.triples((None, None, None)))) == 2
            assert len(set(store.triples((None, None, None), gr_uri))) == 2
            assert len(set(store.triples((None, None, None), gr2_uri))) == 1

            assert gr2_uri in store.contexts()
            assert trp1 not in store.triples((None, None, None))
            assert trp1 not in store.triples((None, None, None),
                    store.DEFAULT_GRAPH_URI)
            assert trp2 in store.triples((None, None, None), gr_uri)
            assert trp2 in store.triples((None, None, None))
            assert trp3 in store.triples((None, None, None), gr2_uri)
            assert trp3 in store.triples((None, None, None),
                    store.DEFAULT_GRAPH_URI)


    def test_delete_from_ctx(self, store):
        '''
        Delete triples from a named graph and from the default graph.
        '''
        gr_uri = URIRef('urn:bogus:graph#a') # From previous test
        gr2_uri = URIRef('urn:bogus:graph#b') # Never created before

        with TxnManager(store, True) as txn:
            store.remove((None, None, None))
            store.remove((None, None, None), gr2_uri)

            assert len(set(store.triples((None, None, None)))) == 0
            assert len(set(store.triples((None, None, None), gr_uri))) == 2
            assert len(set(store.triples((None, None, None), gr2_uri))) == 0
